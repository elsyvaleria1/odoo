import json
import logging
import os
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from odoo import api, fields, models, tools
from odoo.http import request
from odoo.libs.debug_log import DebugLog
from odoo.tools import config, escape_psql
from odoo.tools.assets.esm_registry import esm_registry
from odoo.tools.assets.nodes import (
    AssetNode,
    is_import_map_node,
    owl_compiler_module_node,
)
from odoo.tools.assets.owl_precompile import (
    precompile_templates,
    precompiler_available,
    web_static_path,
)

if TYPE_CHECKING:
    from .ir_attachment import IrAttachment

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

PRECOMPILED_TEMPLATES_URL_PREFIX = "/web/assets/owl/"

_FAILED_RETRY_S = 600.0
_failed_at: dict[tuple[str, str], float] = {}

_RECENT_SCRIPTS = 8

_PREGENERATE_WORKERS = 8
_recent_scripts: OrderedDict[str, str] = OrderedDict()


class IrQweb(models.AbstractModel):
    _inherit = "ir.qweb"

    def _get_asset_nodes(
        self,
        bundle: str,
        css: bool = True,
        js: bool = True,
        debug: str = "",
        defer_load: bool = False,
        lazy_load: bool = False,
        media: str | None = None,
        autoprefix: bool = False,
        page: bool = False,
    ) -> list[AssetNode]:
        nodes = super()._get_asset_nodes(
            bundle,
            css=css,
            js=js,
            debug=debug,
            defer_load=defer_load,
            lazy_load=lazy_load,
            media=media,
            autoprefix=autoprefix,
            page=page,
        )
        if page and js and self._note_page_script_bundle(bundle, debug or ""):
            nodes = self._with_owl_compiler(bundle, nodes)
        return nodes

    @staticmethod
    def _with_owl_compiler(bundle: str, nodes: list[AssetNode]) -> list[AssetNode]:
        maps = [index for index, node in enumerate(nodes) if is_import_map_node(node)]
        if not maps:
            return nodes
        at = maps[-1] + 1
        return [*nodes[:at], owl_compiler_module_node(bundle), *nodes[at:]]

    @api.model
    def _get_eval_free_script_bundles(self) -> set[str]:
        return {
            "web.assets_frontend_lazy",
            "web.assets_frontend_minimal",
            "web.assets_tests",
        }

    def _pregenerate_assets_bundles(self) -> list[str]:
        links = super()._pregenerate_assets_bundles()
        links.extend(self._pregenerate_precompiled_templates())
        return links

    @api.model
    def _warm_page_bundle(self, bundle: str, page_scope: tuple[str, ...] = ()) -> None:
        super()._warm_page_bundle(bundle, page_scope)
        if precompiler_available():
            self._get_page_templates_checksum(
                bundle, self.env["ir.asset"]._prepare_assets_params()
            )

    @api.model
    def _get_awaited_template_bundles(self, assets_params: dict[str, Any]) -> list[str]:
        registry = esm_registry()
        installed = self.env["ir.asset"]._get_addons_installed()
        bundles = dict.fromkeys(sorted(self._get_eval_free_script_bundles()))
        for page in list(bundles):
            for parent in self._get_dynamic_parent_bundles(page, assets_params):
                bundles.update(
                    dict.fromkeys(
                        child
                        for child in registry.dynamic_children.get(parent, ())
                        if registry.bundle_addon(child) in installed
                    )
                )
        return list(bundles)

    @api.model
    def _pregenerate_precompiled_templates(self) -> list[str]:
        if not precompiler_available():
            _debug.logic("pregenerate_templates_skipped", reason="no_precompiler")
            return []
        IrAttachment = self.env["ir.attachment"]
        assets_params = self.env["ir.asset"]._prepare_assets_params()
        variants = (False, True) if self._has_esm_test_satellites("") else (False,)
        hashes = {
            lang: sorted(self._get_translations_hashes(lang))
            for lang, _name in self.env["res.lang"].get_installed()
        }
        failed_params = json.dumps(assets_params, sort_keys=True)
        start = time.time()
        links = []
        jobs = {}
        for bundle in self._get_awaited_template_bundles(assets_params):
            checksum = self._get_asset_bundle(
                bundle, css=False, js=True, assets_params=assets_params
            )._xml.precompile_checksum()
            if checksum is None:
                continue
            for lang, translations_hashes in hashes.items():
                for translations_hash in translations_hashes:
                    for dev in variants:
                        key = (bundle, checksum, lang, translations_hash, dev)
                        url = self._get_precompiled_templates_url(*key[:4], dev=dev)
                        if IrAttachment._search_generated_assets(url, limit=1):
                            links.append(url)
                            continue
                        job = self._prepare_templates_precompile(
                            *key[:4], dev=dev, assets_params=assets_params
                        )
                        if job is not None:
                            jobs[key] = job
        if jobs:
            workers = min(len(jobs), os.cpu_count() or 1, _PREGENERATE_WORKERS)
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = dict(
                    zip(
                        jobs,
                        pool.map(
                            lambda job: precompile_templates(**job), jobs.values()
                        ),
                        strict=True,
                    )
                )
            for (bundle, checksum, lang, translations_hash, dev), result in sorted(
                results.items()
            ):
                url = self._get_precompiled_templates_url(
                    bundle, checksum, lang, translations_hash, dev=dev
                )
                if result is None:
                    _failed_at[url, failed_params] = time.monotonic()
                    continue
                self._store_precompiled_templates(
                    url, bundle, lang, translations_hash, result.script, dev=dev
                )
                links.append(url)
        _logger.info(
            "OWL templates precompiled: %d artifacts, %d compiled, in %.2f seconds",
            len(links),
            len(jobs),
            time.time() - start,
        )
        return links

    @tools.conditional(
        "xml" not in config["dev_mode"],
        tools.ormcache(
            "bundle",
            "tuple(sorted(assets_params.items()))",
            cache="assets",
        ),
    )
    def _get_page_templates_checksum(
        self, bundle: str, assets_params: dict[str, Any]
    ) -> str | None:
        asset_bundle = self._get_asset_bundle(
            bundle, css=False, js=True, assets_params=assets_params
        )
        if asset_bundle.js_rebuild_params:
            return None
        return asset_bundle._xml.precompile_checksum()

    @api.model
    def _get_page_templates_url(
        self, bundle: str, lang: str | None, debug: str = ""
    ) -> str | None:
        if not lang or debug or config["test_enable"] or not precompiler_available():
            return None
        checksum = self._get_page_templates_checksum(
            bundle, self.env["ir.asset"]._prepare_assets_params()
        )
        if checksum is None:
            return None
        IrHttp = self.env["ir.http"]
        translations_hash = IrHttp._get_web_translations_hash(
            IrHttp._get_webclient_translation_modules()[0], lang
        )
        return self._get_precompiled_templates_url(
            bundle, checksum, lang, translations_hash
        )

    @api.model
    def _get_translations_hashes(self, lang: str) -> set[str]:
        IrHttp = self.env["ir.http"]
        return {
            IrHttp._get_web_translations_hash(modules, lang)
            for modules in IrHttp._get_webclient_translation_modules()
        }

    @api.model
    def _note_page_script_bundle(self, bundle: str, debug: str) -> bool:
        needs_eval = self._is_script_bundle_eval_needed(bundle, debug)
        if request:
            request.note_script_bundle(needs_eval=needs_eval)
        return needs_eval

    @api.model
    def _is_script_bundle_eval_needed(self, bundle: str, debug: str) -> bool:
        return bundle not in self._get_eval_free_script_bundles() or (
            self._is_browser_compilation_forced(debug)
        )

    @api.model
    def _is_loaded_bundle_eval_needed(self, bundle: str, debug: str) -> bool:
        assets_params = self.env["ir.asset"]._prepare_assets_params()
        return bundle not in self._get_awaited_template_bundles(assets_params) or (
            self._is_browser_compilation_forced(debug)
        )

    @api.model
    def _is_browser_compilation_forced(self, debug: str) -> bool:
        return (
            self._is_debug_assets(debug)
            or "xml" in config["dev_mode"]
            or not precompiler_available()
        )

    @api.model
    def _precompiled_templates_available(self) -> bool:
        return precompiler_available()

    @api.model
    def _get_precompiled_templates_url(
        self,
        bundle: str,
        checksum: str,
        lang: str,
        translations_hash: str,
        *,
        dev: bool = False,
    ) -> str:
        variant = ".dev" if dev else ""
        return (
            f"{PRECOMPILED_TEMPLATES_URL_PREFIX}"
            f"{checksum}/{lang}/{translations_hash}/{bundle}{variant}.js"
        )

    @api.model
    def _get_or_create_precompiled_template_attachment(
        self,
        bundle: str,
        checksum: str,
        lang: str,
        translations_hash: str,
        *,
        dev: bool = False,
        build: bool = True,
        assets_params: dict[str, Any] | None = None,
    ) -> IrAttachment:
        url = self._get_precompiled_templates_url(
            bundle, checksum, lang, translations_hash, dev=dev
        )
        IrAttachment = self.env["ir.attachment"]
        attachment = IrAttachment._search_generated_assets(url, limit=1)
        if attachment or not build:
            return attachment
        if not precompiler_available():
            return attachment
        if assets_params is None:
            assets_params = self.env["ir.asset"]._prepare_assets_params()
        failed_key = (url, json.dumps(assets_params, sort_keys=True))
        failed_at = _failed_at.get(failed_key)
        if failed_at is not None and time.monotonic() - failed_at < _FAILED_RETRY_S:
            _debug.logic("precompiled_templates_recently_failed", url=url)
            return attachment
        script = _recent_scripts.get(url)
        if script is None:
            script = self._precompile_templates(
                bundle,
                checksum,
                lang,
                translations_hash,
                dev=dev,
                assets_params=assets_params,
            )
            if script is None:
                _failed_at[failed_key] = time.monotonic()
                return attachment
        return self._store_precompiled_templates(
            url, bundle, lang, translations_hash, script, dev=dev
        )

    @api.model
    def _store_precompiled_templates(
        self,
        url: str,
        bundle: str,
        lang: str,
        translations_hash: str,
        script: str,
        *,
        dev: bool = False,
    ):
        _recent_scripts[url] = script
        _recent_scripts.move_to_end(url)
        while len(_recent_scripts) > _RECENT_SCRIPTS:
            _recent_scripts.popitem(last=False)
        IrAttachment = self.env["ir.attachment"]
        attachment = IrAttachment.with_user(api.SUPERUSER_ID).create(
            IrAttachment._prepare_generated_asset_vals(
                name=f"{bundle}.js",
                mimetype="text/javascript",
                raw=script.encode(),
                url=url,
            )
        )
        others = self._get_translations_hashes(lang) - {translations_hash}
        builds = (
            IrAttachment._search_generated_assets(
                url_pattern=self._get_precompiled_templates_url(
                    escape_psql(bundle), "%", escape_psql(lang), "%", dev=dev
                ),
                order="create_date desc, id desc",
            ).filtered(lambda old: old.url.split("/")[6] not in others)
            - attachment
        )
        cutoff = fields.Datetime.now() - timedelta(
            days=IrAttachment._get_esm_gc_grace_days()
        )
        twins = builds.filtered(lambda old: old.url == url)
        stale = twins | (builds - twins)[1:].filtered(
            lambda old: old.create_date < cutoff
        )
        if stale:
            _debug.lifecycle(
                "precompiled_templates_replaced", bundle=bundle, stale=len(stale)
            )
            stale.unlink()
        return attachment

    @api.model
    def _precompile_templates(
        self,
        bundle: str,
        checksum: str,
        lang: str,
        translations_hash: str,
        *,
        dev: bool = False,
        assets_params: dict[str, Any] | None = None,
    ) -> str | None:
        job = self._prepare_templates_precompile(
            bundle,
            checksum,
            lang,
            translations_hash,
            dev=dev,
            assets_params=assets_params,
        )
        if job is None:
            return None
        result = precompile_templates(**job)
        return result.script if result else None

    @api.model
    def _prepare_templates_precompile(
        self,
        bundle: str,
        checksum: str,
        lang: str,
        translations_hash: str,
        *,
        dev: bool = False,
        assets_params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        web_static = web_static_path()
        if web_static is None:
            return None
        pipeline = self._get_asset_bundle(
            bundle, css=False, js=True, assets_params=assets_params
        )._xml
        if pipeline.precompile_checksum() != checksum:
            _debug.logic("precompiled_templates_checksum_mismatch", bundle=bundle)
            return None
        translations = self.env["ir.http"]._get_precompile_translations(
            lang, translations_hash
        )
        if translations is None:
            return None
        return {
            "registrations": pipeline.generate_xml_bundle(),
            "translations": translations,
            "web_static": web_static,
            "label": f"{bundle}/{lang}{'/dev' if dev else ''}",
            "sources": pipeline.inline_template_sources(),
            "page_registrations": pipeline.page_registrations(),
            "dev": dev,
        }
