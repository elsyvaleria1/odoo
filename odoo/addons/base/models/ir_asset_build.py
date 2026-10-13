import hashlib
import logging
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from psycopg.errors import SerializationFailure, UniqueViolation

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.asset_log import get_asset_logger, log_event
from odoo.libs.debug_log import DebugLog
from odoo.tools import escape_psql
from odoo.tools.assets.constants import ESM_BRIDGE_URL_PREFIX, ESM_LIB_URL_PREFIX
from odoo.tools.assets.esm_registry import esm_registry

_debug = DebugLog(__name__)
_attach_log = get_asset_logger("attach")

ESM_URL_PREFIX = "/web/assets/esm/"
_SPEC_FIELDS = ("source_key", "has_metafile", "has_sourcemap", "members")


def get_build_directory(url: str) -> str:
    return "/".join(url.split("/")[:5]) + "/"


def get_build_fingerprint(directories: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(directories)).encode()).hexdigest()[:32]


class IrAssetBuild(models.Model):
    _name = "ir.asset.build"
    _description = "Published Asset Build"
    _order = "id desc"

    kind = fields.Selection(
        selection=[
            ("bundle", "Bundle"),
            ("templates", "Templates"),
            ("standalone", "Standalone Bundle"),
            ("group", "Runtime Group"),
            ("lib", "Served Libraries"),
        ],
        required=True,
    )
    bundle = fields.Char(required=True)
    variant = fields.Char(required=True)
    directories = fields.Json(required=True)
    fingerprint = fields.Char(required=True)
    source_key = fields.Char()
    has_metafile = fields.Boolean()
    has_sourcemap = fields.Boolean()
    members = fields.Json()
    state = fields.Selection(
        selection=[("current", "Current"), ("superseded", "Superseded")],
        default="current",
        required=True,
    )
    superseded_at = fields.Datetime()

    _one_current_build_per_variant = models.UniqueIndex(
        "(kind, bundle, variant) WHERE state = 'current'"
    )
    _one_build_per_content = models.UniqueIndex("(kind, bundle, variant, fingerprint)")
    _source_key_idx = models.Index(
        "(kind, bundle, variant, source_key) WHERE source_key IS NOT NULL"
    )
    _superseded_idx = models.Index("(superseded_at) WHERE state = 'superseded'")

    @api.model
    def _key_domain(self, kind: str, bundle: str, variant: str) -> Domain:
        return Domain(
            [("kind", "=", kind), ("bundle", "=", bundle), ("variant", "=", variant)]
        )

    @api.model
    def _grace(self) -> timedelta:
        return timedelta(days=self.env["ir.attachment"]._get_esm_gc_grace_days())

    @api.model
    def _is_current(self, spec: dict[str, Any]) -> bool:
        current = self.search_fetch(
            self._key_domain(spec["kind"], spec["bundle"], spec["variant"])
            & Domain("fingerprint", "=", get_build_fingerprint(spec["directories"]))
            & Domain("state", "=", "current"),
            [name for name in _SPEC_FIELDS if name in spec],
            limit=1,
        )
        if not current:
            return False
        stale = [
            name
            for name in _SPEC_FIELDS
            if name in spec and current[name] != spec[name]
        ]
        if stale:
            _debug.logic(
                "asset_build.current_stale",
                bundle=spec["bundle"],
                variant=spec["variant"],
                fields=stale,
            )
        return not stale

    @api.model
    def _publish(self, spec: dict[str, Any]) -> IrAssetBuild:
        for attempt in (1, 2):
            try:
                with self.env.cr.savepoint():
                    return self._publish_once(spec)
            except UniqueViolation, SerializationFailure:
                _debug.logic(
                    "asset_build.publish_raced", bundle=spec["bundle"], attempt=attempt
                )
                self.env.invalidate_all()
        log_event(
            _attach_log,
            logging.WARNING,
            "build_publish_deferred",
            kind=spec["kind"],
            bundle=spec["bundle"],
            variant=spec["variant"],
        )
        return self.browse()

    def _publish_once(self, spec: dict[str, Any]) -> IrAssetBuild:
        key = self._key_domain(spec["kind"], spec["bundle"], spec["variant"])
        fingerprint = get_build_fingerprint(spec["directories"])
        same = self.search(key & Domain("fingerprint", "=", fingerprint), limit=1)
        current = self.search(key & Domain("state", "=", "current"))
        values = {name: spec[name] for name in _SPEC_FIELDS if name in spec}
        if same and same == current and all(same[k] == v for k, v in values.items()):
            _debug.logic("asset_build.unchanged", bundle=spec["bundle"], id=same.id)
            return same
        if same and current and same != current:
            same.write({"superseded_at": fields.Datetime.now(), **values})
            _debug.logic(
                "asset_build.grace_extended", bundle=spec["bundle"], id=same.id
            )
            return same
        replaced = current - same
        if replaced:
            replaced.write(
                {"state": "superseded", "superseded_at": fields.Datetime.now()}
            )
            replaced.flush_recordset(["state", "superseded_at"])
        if same:
            same.write({"state": "current", "superseded_at": False, **values})
            action = "recurrent"
        else:
            same = self.create(
                {
                    "kind": spec["kind"],
                    "bundle": spec["bundle"],
                    "variant": spec["variant"],
                    "directories": sorted(spec["directories"]),
                    "fingerprint": fingerprint,
                    **values,
                }
            )
            action = "created"
        log_event(
            _attach_log,
            logging.INFO,
            "build_published",
            kind=spec["kind"],
            bundle=spec["bundle"],
            variant=spec["variant"],
            action=action,
            superseded=len(replaced),
        )
        self._remove_expired_builds_and_get_count(key)
        return same

    @api.model
    def _get_build_reusable(
        self, kind: str, bundle: str, variant: str, source_key: str
    ) -> IrAssetBuild:
        same_sources = (
            Domain("kind", "=", kind)
            & Domain("bundle", "=", bundle)
            & Domain("source_key", "=", source_key)
        )
        build = self.search(
            same_sources & Domain("variant", "=", variant),
            order="state, id desc",
            limit=1,
        )
        by = "variant"
        if not build:
            build = self.search(same_sources, order="state, id desc", limit=1)
            by = "sources" if build else "miss"
        _debug.logic(
            "asset_build.reusable",
            kind=kind,
            bundle=bundle,
            variant=variant,
            source_key=source_key,
            by=by,
            built_for=build.variant if build else None,
            build=build,
        )
        return build

    @api.model
    def _live_directories(self) -> set[str]:
        return {
            directory
            for directories in self.search_fetch([], ["directories"]).mapped(
                "directories"
            )
            for directory in directories
        }

    @api.model
    def _remove_expired_builds_and_get_count(self, domain: Domain | None = None) -> int:
        expired = self.search(
            (domain or Domain.TRUE)
            & Domain("state", "=", "superseded")
            & Domain("superseded_at", "<", fields.Datetime.now() - self._grace())
        )
        if not expired:
            return 0
        released = {directory for build in expired for directory in build.directories}
        count = len(expired)
        expired.unlink()
        rows = self._rows_in(released - self._live_directories())
        log_event(
            _attach_log,
            logging.INFO,
            "builds_swept",
            builds=count,
            rows=len(rows),
        )
        rows.unlink()
        return count

    @api.model
    def _rows_in(self, directories: Iterable[str]) -> Any:
        IrAttachment = self.env["ir.attachment"].sudo()
        directories = sorted(directories)
        if not directories:
            return IrAttachment
        return IrAttachment.search(
            IrAttachment._get_domain_generated_assets()
            & Domain.OR(
                [
                    [("url", "=like", f"{escape_psql(directory)}%")]
                    for directory in directories
                ]
            )
        )

    @api.model
    def _retire_uninstalled(self) -> int:
        registry = esm_registry()
        installed = self.env["ir.asset"]._get_addons_installed()

        def owners(build: IrAssetBuild) -> set[str]:
            if build.kind == "group":
                parents = build.bundle.removeprefix("runtime:").split(":")[0]
                return {registry.bundle_addon(p) for p in parents.split("+")}
            return {registry.bundle_addon(build.bundle.removesuffix(".templates"))}

        orphaned = self.search(
            [("state", "=", "current"), ("kind", "!=", "lib")]
        ).filtered(lambda build: not owners(build) <= installed)
        if orphaned:
            orphaned.write(
                {"state": "superseded", "superseded_at": fields.Datetime.now()}
            )
        _debug.logic("asset_build.retired", builds=len(orphaned))
        return len(orphaned)

    @api.model
    def _remove_orphan_rows_and_get_count(self) -> int:
        IrAttachment = self.env["ir.attachment"].sudo()
        live = self._live_directories()
        candidates = IrAttachment.search_fetch(
            IrAttachment._get_domain_generated_assets()
            & Domain.OR(
                [
                    [("url", "=like", f"{ESM_URL_PREFIX}%")],
                    [("url", "=like", f"{ESM_LIB_URL_PREFIX}%")],
                ]
            )
            & Domain("url", "not like", f"{ESM_BRIDGE_URL_PREFIX}%")
            & Domain("write_date", "<", fields.Datetime.now() - self._grace()),
            ["url"],
        )
        orphans = candidates.filtered(
            lambda row: get_build_directory(row.url) not in live
        )
        _debug.logic(
            "asset_build.orphan_rows", candidates=len(candidates), orphans=len(orphans)
        )
        orphans.unlink()
        return len(orphans)

    @api.autovacuum
    def _gc_asset_builds(self) -> None:
        retired = self._retire_uninstalled()
        swept = self._remove_expired_builds_and_get_count()
        orphans = self._remove_orphan_rows_and_get_count()
        log_event(
            _attach_log,
            logging.INFO,
            "builds_collected",
            retired=retired,
            swept=swept,
            orphan_rows=orphans,
        )
