import gzip
import logging
from compression import zstd
from datetime import timedelta
from typing import Any, Self

from odoo import api, fields, models, tools
from odoo.api import ValuesType
from odoo.exceptions import MissingError
from odoo.fields import Domain
from odoo.http import Stream
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict
from odoo.tools.assets.constants import ESM_BRIDGE_REFRESH_DAYS, ESM_BRIDGE_URL_PREFIX

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

ASSETS_URL_PREFIX = "/web/assets/"

ASSET_ENCODINGS = (
    ("zstd", ".zst", "application/zstd", lambda raw: zstd.compress(raw, 12)),
    ("gzip", ".gz", "application/gzip", lambda raw: gzip.compress(raw, 6, mtime=0)),
)
SOURCE_MAP_SUFFIXES = (
    ".map",
    *(f".map{suffix}" for _encoding, suffix, _mimetype, _compress in ASSET_ENCODINGS),
)
_ENCODED_ASSET_MIMETYPES = frozenset(
    {
        "text/javascript",
        "application/javascript",
        "text/css",
        "application/json",
        "image/svg+xml",
    }
)
_ENCODED_ASSET_FLOOR = 8192


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    _ESM_GC_GRACE_DAYS = 7

    _ESM_BRIDGE_GC_GRACE_DAYS = 90

    _ESM_GC_BATCH = 1000

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        records = super().create(vals_list)
        variants = [
            variant
            for vals in vals_list
            if self._is_generated_asset_vals(vals)
            for variant in self._encoded_asset_variant_vals(vals)
        ]
        if variants:
            _debug.lifecycle("asset_variants_created", count=len(variants))
            super().create(variants)
        return records

    @api.model
    def _encoded_asset_variant_vals(self, vals: dict) -> list[dict]:
        raw = vals.get("raw")
        if (
            not isinstance(raw, bytes)
            or len(raw) < _ENCODED_ASSET_FLOOR
            or vals.get("mimetype") not in _ENCODED_ASSET_MIMETYPES
        ):
            return []
        base = {k: v for k, v in vals.items() if k not in ("datas", "db_datas")}
        return [
            {
                **base,
                "name": vals["name"] + suffix,
                "mimetype": mimetype,
                "raw": compress(raw),
                "url": vals["url"] + suffix,
            }
            for _encoding, suffix, mimetype, compress in ASSET_ENCODINGS
        ]

    @tools.ormcache("self.id", cache="assets")
    def _encoded_asset_variants(self) -> tuple[str, frozendict]:
        self.check_singleton()
        url = self.url or ""
        if (
            not url.startswith(ASSETS_URL_PREFIX)
            or self.file_size < _ENCODED_ASSET_FLOOR
        ):
            return self.mimetype, frozendict()
        ids = self._newest_encoded_variant_ids()
        return self.mimetype, frozendict(
            {
                encoding: ids[url + suffix]
                for encoding, suffix, _mimetype, _compress in ASSET_ENCODINGS
                if url + suffix in ids
            }
        )

    def _get_encoded_asset_variant(self, accept_encodings: Any) -> tuple[Self, str]:
        self.check_singleton()
        __, variants = self._encoded_asset_variants()
        for encoding, _suffix, _mimetype, _compress in ASSET_ENCODINGS:
            if encoding in variants and accept_encodings.quality(encoding) > 0:
                return self.browse(variants[encoding]), encoding
        return self.browse(), ""

    def _get_asset_stream(self, filename: str, accept_encodings: Any = None) -> Stream:
        binary = self.env["ir.binary"]
        if accept_encodings is not None and self.id:
            variant, encoding = self._get_encoded_asset_variant(accept_encodings)
            if variant:
                try:
                    encoded = binary._get_stream_from_record(variant, "raw", filename)
                except MissingError:
                    _debug.logic("asset_encoded_copy_gone", filename=filename)
                    self.env.registry.clear_cache("assets")
                else:
                    encoded.mimetype = self._encoded_asset_variants()[0]
                    encoded.encoding = encoding
                    _debug.logic("asset_encoded", filename=filename, encoding=encoding)
                    return encoded
        return binary._get_stream_from_record(self, "raw", filename)

    def _newest_encoded_variant_ids(self) -> dict[str, int]:
        self.check_singleton()
        ids: dict[str, int] = {}
        for variant in self._search_generated_assets(
            urls=[self.url + suffix for _encoding, suffix, _m, _c in ASSET_ENCODINGS]
        ):
            ids[variant.url] = max(ids.get(variant.url, 0), variant.id)
        return ids

    def _encoded_variants(self) -> Self:
        variant_urls = [
            url + suffix
            for url in self.mapped("url")
            if url and url.startswith(ASSETS_URL_PREFIX)
            for _encoding, suffix, _mimetype, _compress in ASSET_ENCODINGS
        ]
        if not variant_urls:
            return self.browse()
        return self._search_generated_assets(urls=variant_urls)

    def unlink(self) -> bool:
        clear_assets = any(
            url and url.startswith(ASSETS_URL_PREFIX) for url in self.mapped("url")
        )
        if clear_assets:
            if variants := self._encoded_variants() - self:
                variants.unlink()
        res = super().unlink()
        if clear_assets:
            _debug.lifecycle(
                "assets_cache_cleared", reason="attachment_unlink", count=len(self)
            )
            self.env["ir.asset"]._invalidate_assets_cache()
        return res

    @api.model
    def _prepare_generated_asset_vals(
        self, *, name: str, mimetype: str, raw: bytes, url: str
    ) -> dict:
        return {
            "name": name,
            "mimetype": mimetype,
            "res_model": "ir.ui.view",
            "res_id": False,
            "type": "binary",
            "public": True,
            "raw": raw,
            "url": url,
        }

    @api.model
    def _withheld_source_maps(self) -> Domain | None:
        if self.env.su or self.env.is_system():
            return None
        if (
            self.env.registry.settings.get(self.env, "web.esbuild.source_maps", "")
            == "linked"
        ):
            return None
        return Domain.OR(
            Domain("url", "=like", f"{ASSETS_URL_PREFIX}%{suffix}")
            for suffix in SOURCE_MAP_SUFFIXES
        ) & Domain("res_model", "=", "ir.ui.view")

    @api.model
    def _withholds(self, url: str | None, res_model: str | None) -> bool:
        return bool(
            url
            and url.startswith(ASSETS_URL_PREFIX)
            and url.endswith(SOURCE_MAP_SUFFIXES)
            and res_model == "ir.ui.view"
            and self._withheld_source_maps() is not None
        )

    @api.model
    def _is_generated_asset_vals(self, values: dict) -> bool:
        return bool(
            (values.get("url") or "").startswith(ASSETS_URL_PREFIX)
            and values.get("res_model") == "ir.ui.view"
            and not values.get("res_id")
            and values.get("public")
        )

    @api.model
    def _is_content_index_required(self, values: dict) -> bool:
        if self._is_generated_asset_vals(values):
            _debug.logic("index_skipped", reason="generated_asset")
            return False
        return super()._is_content_index_required(values)

    @api.model
    def _get_domain_generated_assets(
        self,
        url: str | None = None,
        url_pattern: str | None = None,
        urls: list[str] | None = None,
    ) -> Domain:
        if urls is not None:
            url_leaf = ("url", "in", urls)
        elif url:
            url_leaf = ("url", "=", url)
        elif url_pattern:
            url_leaf = ("url", "=like", url_pattern)
        else:
            url_leaf = ("url", "=like", f"{ASSETS_URL_PREFIX}%")
        return Domain(
            [
                ("public", "=", True),
                ("res_model", "=", "ir.ui.view"),
                ("res_id", "=", 0),
                ("create_uid", "=", api.SUPERUSER_ID),
                url_leaf,
            ]
        )

    @api.model
    def _search_generated_assets(
        self,
        url: str | None = None,
        url_pattern: str | None = None,
        limit: int | None = None,
        order: str | None = None,
        urls: list[str] | None = None,
    ) -> Self:
        return self.sudo().search(
            self._get_domain_generated_assets(
                url=url, url_pattern=url_pattern, urls=urls
            ),
            limit=limit,
            order=order,
        )

    @api.model
    def _get_esm_bridge_gc_grace_days(self) -> int:
        configured = self.env.registry.settings.get_int(
            self.env, "web.esm.bridge_gc_grace_days", self._ESM_BRIDGE_GC_GRACE_DAYS
        )
        _debug.logic(
            "esm_bridge_gc_grace",
            configured=configured,
            floor=int(2 * ESM_BRIDGE_REFRESH_DAYS) + 1,
        )
        return max(int(2 * ESM_BRIDGE_REFRESH_DAYS) + 1, configured)

    @api.model
    def _get_esm_gc_grace_days(self) -> int:
        return max(
            1,
            self.env.registry.settings.get_int(
                self.env, "web.esm.gc_grace_days", self._ESM_GC_GRACE_DAYS
            ),
        )

    @api.autovacuum
    def _gc_esm_bridges(self) -> tuple[int, int]:
        cutoff = fields.Datetime.now() - timedelta(
            days=self._get_esm_bridge_gc_grace_days()
        )
        domain = self._get_domain_generated_assets(
            url_pattern=f"{ESM_BRIDGE_URL_PREFIX}%.js"
        ) & Domain("write_date", "<", cutoff)
        aged = self.sudo().search(domain, limit=self._ESM_GC_BATCH)
        _debug.lifecycle("esm_bridges_gc", aged=len(aged), batch=self._ESM_GC_BATCH)
        if aged:
            with _debug.perf("esm_gc_unlink", cr=self.env.cr, count=len(aged)):
                aged.unlink()
            _logger.info("GC'd %d aged ESM bridge shim(s)", len(aged))
        remaining = (
            self.sudo().search_count(domain) if len(aged) == self._ESM_GC_BATCH else 0
        )
        return len(aged), remaining

    @api.model
    def regenerate_assets_bundles(self) -> None:
        self._check_admin_access()
        generated = self.search(self._get_domain_generated_assets())
        builds = self.env["ir.asset.build"].sudo().search([])
        _debug.lifecycle(
            "regenerate_assets_bundles", generated=len(generated), builds=len(builds)
        )
        builds.unlink()
        if generated:
            with _debug.perf(
                "regenerate_unlink", cr=self.env.cr, generated=len(generated)
            ):
                generated.unlink()
        else:
            _debug.lifecycle("assets_cache_cleared", reason="regenerate_no_generated")
            self.env.registry.clear_cache("assets")
