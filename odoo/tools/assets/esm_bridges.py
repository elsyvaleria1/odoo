import logging
from collections.abc import Collection, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple
from urllib.parse import quote

from odoo import modules
from odoo.api import SUPERUSER_ID, Environment
from odoo.fields import Domain
from odoo.libs.asset_log import get_asset_logger, log_event
from odoo.libs.debug_log import DebugLog
from odoo.libs.hashing import cache_hash
from odoo.orm._protocols import IrAttachmentProtocol
from odoo.tools import config
from odoo.tools.assets.constants import ESM_BRIDGE_REFRESH_DAYS, ESM_BRIDGE_URL_PREFIX
from odoo.tools.assets.esm_graph import (
    ModuleSource,
    ModuleSourceMap,
    _bridge_shim_source,
    _BridgeExportResolver,
    _extract_esm_exports,
    _get_import_specifiers,
    _resolve_export_specifier,
    _strict_stub_source,
)
from odoo.tools.assets.esm_lexer import get_evaluation_uses, lex_module
from odoo.tools.assets.esm_registry import esm_registry, external_libs

__all__ = ["BridgeShimManager"]

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)
_bridge_log = get_asset_logger("bridge")


def _is_rw_escalation_expected() -> bool:
    return bool(modules.module.current_test) or config["test_enable"]


def _log_bridge_creation_failure() -> None:
    expected = _is_rw_escalation_expected()
    _logger.log(
        logging.DEBUG if expected else logging.WARNING,
        "Bridge attachment escalation to a read-write cursor "
        "failed; falling back to data: URIs",
        exc_info=not expected,
    )


class BridgeUse(NamedTuple):
    module: str
    specifier: str
    binding: str
    line: int


class _BridgeShimSources(NamedTuple):
    sources_by_specifier: dict[str, str]
    star_fallback_specifiers: tuple[str, ...]


class _ParentBridgeShimSources(NamedTuple):
    sources_by_specifier: dict[str, str]
    skipped_tests: int
    skip_legacy_tests: bool


class _BridgeUrls(NamedTuple):
    urls_by_specifier: dict[str, str]
    star_fallback_count: int


class _BridgeUrlContents(NamedTuple):
    urls_by_specifier: dict[str, str]
    contents_by_url: dict[str, str]


class PageProvidedBridgeUrls(NamedTuple):
    urls_by_specifier: dict[str, str]
    per_file_specifiers: set[str]


def _prepare_bridge_url_contents(
    sources_by_specifier: dict[str, str],
) -> _BridgeUrlContents:
    urls_by_specifier: dict[str, str] = {}
    contents_by_url: dict[str, str] = {}
    for specifier, content in sources_by_specifier.items():
        content_hash = cache_hash(content.encode("utf-8"))[:32]
        url = f"{ESM_BRIDGE_URL_PREFIX}{content_hash}.js"
        urls_by_specifier[specifier] = url
        contents_by_url[url] = content
    return _BridgeUrlContents(urls_by_specifier, contents_by_url)


def _prepare_inline_bridge_urls(
    contents: _BridgeUrlContents, missing_urls: set[str]
) -> dict[str, str]:
    return {
        specifier: (
            url
            if url not in missing_urls
            else f"data:text/javascript;charset=utf-8,{quote(contents.contents_by_url[url])}"
        )
        for specifier, url in contents.urls_by_specifier.items()
    }


def _prepare_bridge_shim_sources(
    specifiers: Iterable[str],
    resolver: _BridgeExportResolver,
    *,
    strict: bool = False,
    wait: bool = False,
) -> _BridgeShimSources:
    sources_by_specifier: dict[str, str] = {}
    star_fallback_specifiers: list[str] = []
    for specifier in sorted(specifiers):
        names, has_default = resolver.source_exports(specifier)
        if strict:
            sources_by_specifier[specifier] = _strict_stub_source(specifier, names)
            continue
        shim, is_star_fallback = _bridge_shim_source(
            specifier, names, has_default, wait=wait
        )
        sources_by_specifier[specifier] = shim
        if is_star_fallback:
            star_fallback_specifiers.append(specifier)
    return _BridgeShimSources(sources_by_specifier, tuple(star_fallback_specifiers))


def get_evaluation_time_bridge_uses(
    modules: Iterable[ModuleSource], bridged: Collection[str]
) -> list[BridgeUse]:
    bridged = frozenset(bridged)
    found: list[BridgeUse] = []
    for module in modules:
        source = module.raw_content
        lexed = lex_module(source)
        if not lexed:
            continue
        url = getattr(module, "url", None)
        targets = {
            spec: _resolve_export_specifier(module.module_path, spec, url)
            for spec in lexed.get("specifiers", ())
        }
        if bridged.isdisjoint(targets.values()):
            continue
        for use in get_evaluation_uses(source) or ():
            target = targets.get(use["n"])
            if target in bridged:
                found.append(
                    BridgeUse(module.module_path, target, use["name"], use["line"])
                )
    _debug.logic(
        "esm_bridges.evaluation_time_uses", bridged=len(bridged), found=len(found)
    )
    return found


class BridgeShimManager:
    def __init__(
        self,
        env: Environment,
        bundle_name: str,
        native_modules: Sequence[ModuleSource],
    ) -> None:
        self.env = env
        self.bundle_name = bundle_name
        self.native_modules = native_modules

    def _update_reused_shim_dates(self, existing: IrAttachmentProtocol) -> None:
        if not existing:
            return
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
            days=ESM_BRIDGE_REFRESH_DAYS
        )
        stale = [
            row.id
            for row in existing
            if row["write_date"] and row["write_date"] < cutoff
        ]
        if not stale:
            return
        cr: Any = self.env.cr
        if cr.readonly:
            log_event(
                _bridge_log,
                logging.DEBUG,
                "bridges_refresh_skipped_readonly",
                bundle=self.bundle_name,
                rows=len(stale),
            )
            return
        cr.execute(
            "UPDATE ir_attachment SET write_date = now() at time zone 'UTC'"
            " WHERE id = ANY(%s)",
            (stale,),
        )
        self.env["ir.attachment"].browse(stale).invalidate_recordset(["write_date"])
        log_event(
            _bridge_log,
            logging.DEBUG,
            "bridges_refreshed",
            bundle=self.bundle_name,
            rows=len(stale),
        )

    def _get_or_create_bridge_urls(
        self,
        shims_by_spec: dict[str, str],
    ) -> dict[str, str]:
        if not shims_by_spec:
            return {}
        contents = _prepare_bridge_url_contents(shims_by_spec)
        url_by_spec = contents.urls_by_specifier
        content_by_url = contents.contents_by_url
        Attachment = self.env["ir.attachment"].sudo()
        existing = Attachment.search_fetch(
            Attachment._get_domain_generated_assets()
            & Domain("url", "in", list(content_by_url)),
            ["url", "write_date"],
        )
        existing_urls = set(existing.mapped("url"))
        _debug.logic(
            "esm_bridges.shims_persisting",
            bundle=self.bundle_name,
            shims=len(shims_by_spec),
            urls=len(content_by_url),
            reused=len(existing_urls),
        )
        self._update_reused_shim_dates(existing)
        to_create = [
            Attachment._prepare_generated_asset_vals(
                name=url.rsplit("/", 1)[-1],
                mimetype="text/javascript",
                raw=content.encode("utf-8"),
                url=url,
            )
            for url, content in content_by_url.items()
            if url not in existing_urls
        ]
        if not to_create:
            return url_by_spec

        from odoo.http import request

        outside_request = not request
        if outside_request:
            self.env["ir.attachment"].with_user(SUPERUSER_ID).create(to_create)
        else:
            try:
                self._create_bridge_attachments_via_rw_cursor(to_create)
            except Exception:
                _log_bridge_creation_failure()
                missing_urls = {item["url"] for item in to_create}
                return self._prepare_fallback_bridge_urls(contents, missing_urls)
        log_event(
            _bridge_log,
            logging.INFO,
            "bridges_persisted",
            bundle=self.bundle_name,
            new=len(to_create),
            reused=len(content_by_url) - len(to_create),
            total=len(url_by_spec),
        )
        return url_by_spec

    def _create_bridge_attachments_via_rw_cursor(
        self, to_create: list[dict[str, Any]]
    ) -> None:
        with self.env.registry.cursor(readonly=False) as rw_cr:
            rw_env = Environment(rw_cr, SUPERUSER_ID, {})
            rw_env["ir.attachment"].create(to_create)

    def _prepare_fallback_bridge_urls(
        self, contents: _BridgeUrlContents, missing_urls: set[str]
    ) -> dict[str, str]:
        log_event(
            _bridge_log,
            logging.DEBUG if _is_rw_escalation_expected() else logging.WARNING,
            "bridges_inlined_no_rw_cursor",
            bundle=self.bundle_name,
            inline=len(missing_urls),
            reused=len(contents.contents_by_url) - len(missing_urls),
            total=len(contents.urls_by_specifier),
        )
        return _prepare_inline_bridge_urls(contents, missing_urls)

    def _prepare_parent_self_shim_sources(self) -> _ParentBridgeShimSources:
        source_map = ModuleSourceMap(self.native_modules)
        exports_cache: dict[str, set[str]] = {}

        shims_by_spec: dict[str, str] = {}
        skip_legacy_tests = self.bundle_name in esm_registry().import_map_includes
        skipped_tests = 0
        for asset in self.native_modules:
            specifier = asset.module_path
            if not specifier.startswith("@"):
                continue
            if skip_legacy_tests and "/static/tests/" in (
                getattr(asset, "url", None) or ""
            ):
                skipped_tests += 1
                continue
            src = asset.raw_content
            names, _ = _extract_esm_exports(
                src,
                source_map=source_map,
                importing_specifier=specifier,
                importing_url=getattr(asset, "url", None) or None,
                _exports_cache=exports_cache,
            )
            shim, _star = _bridge_shim_source(specifier, names, has_default=False)
            shims_by_spec[specifier] = shim

        return _ParentBridgeShimSources(shims_by_spec, skipped_tests, skip_legacy_tests)

    def _get_or_create_parent_self_bridge_urls(self) -> dict[str, str]:
        sources = self._prepare_parent_self_shim_sources()
        bridges = self._get_or_create_bridge_urls(sources.sources_by_specifier)
        log_event(
            _bridge_log,
            logging.DEBUG,
            "parent_self_bridge",
            bundle=self.bundle_name,
            shims=len(bridges),
        )
        _debug.pipeline(
            "esm_bridges.parent_self_bridge",
            bundle=self.bundle_name,
            modules=len(self.native_modules),
            shims=len(bridges),
            skipped_tests=sources.skipped_tests,
            skip_legacy_tests=sources.skip_legacy_tests,
        )
        return bridges

    def _discover_bridge_specifiers(
        self,
        native_specifiers: set[str],
        ext_lib_names: set[str],
        modules: Sequence[ModuleSource] | None = None,
    ) -> tuple[dict[str, None], set[str]]:
        if modules is None:
            modules = self.native_modules
        discovered: dict[str, None] = {}
        ignored = native_specifiers | {"@odoo/owl"} | ext_lib_names
        ext_seen: set[str] = set()
        for asset in modules:
            for specifier in sorted(_get_import_specifiers(asset.raw_content)):
                if not specifier.startswith("@"):
                    continue
                if specifier in ext_lib_names:
                    ext_seen.add(specifier)
                elif specifier not in ignored:
                    discovered[specifier] = None
        _debug.pipeline(
            "esm_bridges.static_edges",
            bundle=self.bundle_name,
            modules=len(modules),
            discovered=len(discovered),
            ext_libs=len(ext_seen),
        )
        return discovered, ext_seen

    def _discover_reachable_specifiers(
        self,
        native_specifiers: set[str],
        ext_lib_names: set[str],
        provided: frozenset[str] | set[str],
        modules: Sequence[ModuleSource] | None = None,
        resolver: _BridgeExportResolver | None = None,
    ) -> tuple[dict[str, None], set[str]]:
        discovered, ext_seen = self._discover_bridge_specifiers(
            native_specifiers, ext_lib_names, modules
        )
        if resolver is None:
            resolver = _BridgeExportResolver(external_libs(), self.bundle_name)
        ignored = native_specifiers | {"@odoo/owl"} | ext_lib_names
        queue = [spec for spec in discovered if spec not in provided]
        visited: set[str] = set()
        while queue:
            spec = queue.pop()
            if spec in visited:
                continue
            visited.add(spec)
            src = resolver.read_source(spec)
            if src is None:
                continue
            for specifier in _lexed_imports(
                src, base_spec=spec, base_url=resolver.effective_url(spec)
            ):
                if specifier in ext_lib_names:
                    ext_seen.add(specifier)
                    continue
                if specifier in ignored:
                    continue
                discovered[specifier] = None
                if specifier not in provided and specifier not in visited:
                    queue.append(specifier)
        _debug.pipeline(
            "esm_bridges.reachable",
            bundle=self.bundle_name,
            provided=len(provided),
            visited=len(visited),
            discovered=len(discovered),
            ext_libs=len(ext_seen),
        )
        return discovered, ext_seen

    def prepare_shim_sources(
        self, specifiers: set[str], *, strict: bool = False, wait: bool = False
    ) -> dict[str, str]:
        if not specifiers:
            return {}
        resolver = _BridgeExportResolver(external_libs(), self.bundle_name)
        with _debug.perf(
            "esm_bridges.shim_sources",
            bundle=self.bundle_name,
            specifiers=len(specifiers),
            strict=strict,
            wait=wait,
        ):
            sources = _prepare_bridge_shim_sources(
                specifiers, resolver, strict=strict, wait=wait
            )
        return sources.sources_by_specifier

    def _get_or_create_native_to_legacy_bridge_urls(
        self,
        native_specifiers: set[str],
        modules: Sequence[ModuleSource] | None = None,
    ) -> dict[str, str]:
        if modules is None:
            modules = self.native_modules
        discovered, ext_seen = self._discover_bridge_specifiers(
            native_specifiers, set(external_libs()), modules=modules
        )
        bridge_map, star_fallback = self._get_or_create_bridge_urls_and_fallback_count(
            discovered
        )
        log_event(
            _bridge_log,
            logging.DEBUG,
            "build",
            bundle=self.bundle_name,
            shims=len(bridge_map),
            discovered=len(discovered),
            native_files=len(modules),
            star_fallback=star_fallback,
            ext_libs_skipped=len(ext_seen),
            ext_libs=",".join(sorted(ext_seen)) or "-",
        )
        return bridge_map

    def _get_or_create_bridge_urls_and_fallback_count(
        self,
        discovered: Iterable[str],
        resolver: _BridgeExportResolver | None = None,
    ) -> _BridgeUrls:
        if resolver is None:
            resolver = _BridgeExportResolver(external_libs(), self.bundle_name)
        sources = _prepare_bridge_shim_sources(discovered, resolver)
        for specifier in sources.star_fallback_specifiers:
            _debug.logic(
                "esm_bridges.star_fallback",
                bundle=self.bundle_name,
                spec=specifier,
            )
        return _BridgeUrls(
            self._get_or_create_bridge_urls(sources.sources_by_specifier),
            len(sources.star_fallback_specifiers),
        )

    def get_or_create_page_provided_bridge_urls(
        self,
        native_specifiers: set[str],
        provided: frozenset[str] | set[str],
        modules: Sequence[ModuleSource] | None = None,
    ) -> PageProvidedBridgeUrls:
        if modules is None:
            modules = self.native_modules
        resolver = _BridgeExportResolver(external_libs(), self.bundle_name)
        discovered, _ext = self._discover_reachable_specifiers(
            native_specifiers,
            set(external_libs()),
            provided,
            modules=modules,
            resolver=resolver,
        )
        bridged = [spec for spec in discovered if spec in provided]
        bridge_map, star_fallback = self._get_or_create_bridge_urls_and_fallback_count(
            bridged, resolver
        )
        per_file = discovered.keys() - set(bridged)
        log_event(
            _bridge_log,
            logging.DEBUG,
            "page_provided",
            bundle=self.bundle_name,
            bridged=len(bridge_map),
            per_file=len(per_file),
            star_fallback=star_fallback,
        )
        return PageProvidedBridgeUrls(bridge_map, per_file)


def _lexed_imports(
    src: str, *, base_spec: str, base_url: str | None = None
) -> list[str]:
    out: list[str] = []
    for specifier in sorted(_get_import_specifiers(src)):
        if specifier.startswith("."):
            resolved = _resolve_export_specifier(base_spec, specifier, base_url)
            if resolved is None:
                continue
            specifier = resolved
        elif not specifier.startswith("@"):
            continue
        out.append(specifier)
    return out
