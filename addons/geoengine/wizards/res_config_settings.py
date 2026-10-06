import logging

import psycopg

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from ..models.base import COUNTRY_EXTENTS
from ..models.fields import GeoField, create_geo_index
from ..models.geo_types import parse_extent

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    enable_geometry_validation = fields.Boolean(
        default=True,
        config_parameter="geoengine.validate_geometry",
        help="Check geometries before saving. When disabled, invalid geometry "
        "reaches PostGIS unchecked and fails there instead.",
    )
    auto_repair_geometry = fields.Boolean(
        default=True,
        config_parameter="geoengine.auto_repair_geometry",
        help="Repair invalid geometry with ST_MakeValid instead of rejecting "
        "it. Only applies while geometry validation is enabled.",
    )
    max_geometry_size = fields.Integer(
        default=1000000,
        config_parameter="geoengine.max_geometry_size",
        help="Largest single geometry accepted, in bytes of WKT.",
    )

    geoengine_map_extent = fields.Char(
        config_parameter="geoengine.default_map_extent",
        help="Default map extent as: min_x, min_y, max_x, max_y in Web Mercator "
        "(EPSG:3857).\n"
        "Leave empty to fall back to the company country, then to Europe.\n"
        "Common values:\n"
        "- Mexico: -13173896.503, 1632778.928, -9633272.717, 3910375.796\n"
        "- USA: -14764617.394, 2273030.926, -6679169.448, 7074326.998\n"
        "- World: -20037508.34, -20037508.34, 20037508.34, 20037508.34",
    )

    @api.constrains("max_geometry_size")
    def _check_max_geometry_size(self) -> None:
        for record in self:
            if record.max_geometry_size <= 0:
                raise ValidationError(self.env._("Max geometry size must be positive"))

    @api.constrains("geoengine_map_extent")
    def _check_geoengine_map_extent(self) -> None:
        for record in self:
            raw = record.geoengine_map_extent
            if raw and parse_extent(raw) is None:
                raise ValidationError(
                    self.env._(
                        "Default map extent must be four comma-separated numbers "
                        "'min_x, min_y, max_x, max_y', with min_x/min_y smaller "
                        "than max_x/max_y. Got: %(value)s",
                        value=raw,
                    )
                )

    def _spatial_index_targets(self) -> list[tuple[str, str]]:
        return sorted(
            (model_cls._table, field_name)
            for model_cls in self.env.registry.models.values()
            if model_cls._auto and not model_cls._abstract
            for field_name, field in model_cls._fields.items()
            if isinstance(field, GeoField) and field.store
        )

    def _create_spatial_indexes(self, *, rebuild: bool) -> tuple[int, list[str]]:
        cr = self.env.cr
        built, failed = 0, []
        for table_name, field_name in self._spatial_index_targets():
            try:
                with cr.savepoint():
                    built += create_geo_index(
                        cr, table_name, field_name, rebuild=rebuild
                    )
            except psycopg.Error as e:
                _logger.warning(
                    "Failed to build index for %s.%s: %s", table_name, field_name, e
                )
                failed.append(f"{table_name}.{field_name}")
        return built, failed

    def _spatial_index_notification(
        self, verb: str, built: int, failed: list[str]
    ) -> dict:
        if failed:
            message = self.env._(
                "%(verb)s %(built)d spatial index(es). %(failed)d failed: "
                "%(names)s — see the server log.",
                verb=verb,
                built=built,
                failed=len(failed),
                names=", ".join(failed[:5]),
            )
        else:
            message = self.env._(
                "%(verb)s %(built)d spatial index(es).", verb=verb, built=built
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Success") if not failed else self.env._("Partial"),
                "message": message,
                "type": "success" if not failed else "warning",
                "sticky": bool(failed),
            },
        }

    def action_rebuild_spatial_indexes(self):
        built, failed = self._create_spatial_indexes(rebuild=True)
        return self._spatial_index_notification(self.env._("Rebuilt"), built, failed)

    def action_create_missing_spatial_indexes(self):
        built, failed = self._create_spatial_indexes(rebuild=False)
        return self._spatial_index_notification(self.env._("Created"), built, failed)

    def action_set_country_extent(self):
        company = self.env.company

        if not (country_id := company.country_id):
            return self._notify(
                self.env._("Info"),
                self.env._("No country set for the current company."),
            )

        country_code = (country_id.code or "").upper()
        if country_code not in COUNTRY_EXTENTS:
            return self._notify(
                self.env._("Info"),
                self.env._(
                    "No predefined extent for %(country)s. Please set the "
                    "extent manually.",
                    country=country_id.name,
                ),
            )

        self.geoengine_map_extent = COUNTRY_EXTENTS[country_code]
        return self._notify(
            self.env._("Success"),
            self.env._(
                "Map extent set for %(country)s: %(extent)s",
                country=country_id.name,
                extent=COUNTRY_EXTENTS[country_code],
            ),
        )

    def _notify(self, title: str, message: str) -> dict:
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {"title": title, "message": message, "sticky": False},
        }
