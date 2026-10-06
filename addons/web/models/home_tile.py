import logging
import re
from datetime import timedelta
from typing import Any

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import get_lang

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)

TILE_ID_RE = re.compile(r"[\w.:-]{1,64}", re.ASCII)
FIELD_NAME_RE = re.compile(r"[a-z_][a-z0-9_]{0,62}", re.ASCII)
METRIC_FIELD_TYPES = frozenset({"integer", "float", "monetary"})


class TileUnavailable(Exception):
    pass


class HomeTile(models.AbstractModel):
    _name = "home.tile"
    _description = "Home Dashboard Tile"

    _TILES_PER_CALL = 50
    _RECENT_RECORDS_LIMIT = 12
    _METRIC_WEEKS = 8
    _METRIC_CHOICES_LIMIT = 200

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            "recent_records": {
                "name": self.env._("Recently opened"),
                "sizes": ["1x1", "2x1"],
                "model": "web.recent.record",
            },
            "metric": {
                "name": self.env._("Metric"),
                "sizes": ["1x1", "2x1"],
                "model": "ir.filters",
            },
        }

    @api.model
    def _get_starter_tiles(self) -> list[dict[str, str]]:
        return [{"id": "recent_records_1", "type": "recent_records", "size": "2x1"}]

    @api.readonly
    @api.model
    def get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            tile_type: {"name": spec["name"], "sizes": spec["sizes"]}
            for tile_type, spec in self._get_tile_types().items()
            if self._may_use(spec)
        }

    @api.model
    def _may_use(self, spec: dict[str, Any]) -> bool:
        if not self.env.user._is_internal():
            return False
        model = spec.get("model")
        if model and not (model in self.env and self.env[model].has_access("read")):
            return False
        # a tile that summarises a screen reaches whoever that screen's menu does
        menu = spec.get("menu")
        return not menu or self._menu_visible(menu)

    @api.model
    def _menu_visible(self, xmlid: str) -> bool:
        menu_id = self.env["ir.model.data"]._xmlid_to_res_id(
            xmlid, raise_if_not_found=False
        )
        return (
            bool(menu_id) and menu_id in self.env["ir.ui.menu"]._get_visible_menu_ids()
        )

    @api.readonly
    @api.model
    def get_tiles(self, requests: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not isinstance(requests, list) or len(requests) > self._TILES_PER_CALL:
            raise ValidationError(self.env._("Invalid tile request."))
        with _debug.perf("get_tiles", cr=self.env.cr, tiles=len(requests)) as span:
            tile_types = self._get_tile_types()
            results = {}
            for request in requests:
                if not isinstance(request, dict):
                    raise ValidationError(self.env._("Invalid tile request."))
                tile_id, tile_type = request.get("id"), request.get("type")
                if (
                    not isinstance(tile_id, str)
                    or not TILE_ID_RE.fullmatch(tile_id)
                    or not isinstance(tile_type, str)
                ):
                    raise ValidationError(self.env._("Invalid tile request."))
                spec = tile_types.get(tile_type)
                if spec is None or not self._may_use(spec):
                    results[tile_id] = {"error": "unavailable"}
                    _debug.logic(
                        "tile_unavailable", tile=tile_id, type=request.get("type")
                    )
                    continue
                settings = (
                    self._normalize_tile_settings(
                        request["type"], request.get("settings")
                    )
                    or {}
                )
                try:
                    with self.env.cr.savepoint():
                        data = getattr(self, f"_get_tile_{request['type']}_data")(
                            settings
                        )
                except (TileUnavailable, AccessError) as error:
                    results[tile_id] = {"error": "unavailable"}
                    _debug.logic(
                        "tile_unavailable",
                        tile=tile_id,
                        type=request["type"],
                        reason=type(error).__name__,
                    )
                    continue
                except Exception:
                    _logger.exception(
                        "Home tile %r of type %r failed", tile_id, request["type"]
                    )
                    results[tile_id] = {"error": "failed"}
                    continue
                results[tile_id] = {"data": data}
            span.set(
                failed=sum(r.get("error") == "failed" for r in results.values()),
                unavailable=sum(
                    r.get("error") == "unavailable" for r in results.values()
                ),
            )
        return results

    @api.model
    def _get_tile_recent_records_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        return {
            "records": self.env["web.recent.record"]._get_recent(
                self._RECENT_RECORDS_LIMIT
            )
        }

    @api.model
    def _normalize_tile_settings(
        self, tile_type: str, settings: Any
    ) -> dict[str, Any] | None:
        normalize = getattr(self, f"_normalize_tile_{tile_type}_settings", None)
        if normalize is None:
            return {}
        if settings is None:
            settings = {}
        return normalize(settings) if isinstance(settings, dict) else None

    @api.model
    def _normalize_tile_metric_settings(
        self, settings: dict[str, Any]
    ) -> dict[str, Any] | None:
        filter_id = settings.get("filter_id")
        measure = settings.get("measure") or "__count"
        if filter_id is None:
            return {}
        if (
            not isinstance(filter_id, int)
            or isinstance(filter_id, bool)
            or filter_id <= 0
            or not isinstance(measure, str)
            or (measure != "__count" and not FIELD_NAME_RE.fullmatch(measure))
        ):
            return None
        return {"filter_id": filter_id, "measure": measure}

    @api.model
    def _metric_measure(self, model: models.BaseModel, measure: str) -> Any:
        if measure == "__count":
            return None
        field = model._fields.get(measure)
        if (
            field is None
            or field.type not in METRIC_FIELD_TYPES
            or not field.store
            or not field.aggregator
            or not model._has_field_access(field, "read")
        ):
            raise TileUnavailable
        return field

    @api.model
    def _metric_domain(self, favourite: models.BaseModel) -> list | None:
        try:
            return favourite._get_domain_evaluated()
        except ValueError:
            return None

    @api.model
    def _get_tile_metric_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        if not settings.get("filter_id"):
            return {"configured": False}
        favourite = (
            self.env["ir.filters"]
            .browse(settings["filter_id"])
            .exists()
            ._filtered_access("read")
        )
        if not favourite or favourite.model_id not in self.env:
            raise TileUnavailable
        model = self.env[favourite.model_id]
        domain = self._metric_domain(favourite)
        if domain is None or not model.has_access("read"):
            raise TileUnavailable
        field = self._metric_measure(model, settings["measure"])
        aggregate = f"{field.name}:{field.aggregator}" if field else "__count"
        with _debug.perf("metric_tile", cr=self.env.cr, model=model._name) as span:
            [(value,)] = model._read_group(domain, [], [aggregate])
            today = fields.Date.context_today(self)
            first_weekday = int(get_lang(self.env).week_start) - 1
            first_week = today - timedelta(
                days=(today.weekday() - first_weekday) % 7
                + 7 * (self._METRIC_WEEKS - 1)
            )
            weekly = {
                week.date(): week_value
                for week, week_value in model._read_group(
                    Domain.AND(
                        [
                            domain,
                            [("create_date", ">=", fields.Date.to_string(first_week))],
                        ]
                    ),
                    ["create_date:week"],
                    [aggregate],
                )
                if week
            }
            span.set(weeks=len(weekly))
        return {
            "configured": True,
            "name": favourite.name,
            "model": model._name,
            "model_name": self.env["ir.model"]._get(model._name).name,
            "domain": domain,
            "label": field.get_description(self.env)["string"]
            if field
            else self.env._("Records"),
            "value": value or 0,
            "spark": [
                weekly.get(first_week + timedelta(weeks=week), 0) or 0
                for week in range(self._METRIC_WEEKS)
            ],
        }

    @api.readonly
    @api.model
    def get_metric_choices(self) -> list[dict[str, Any]]:
        if not self._may_use(self._get_tile_types()["metric"]):
            return []
        favourites = self.env["ir.filters"].search([], limit=self._METRIC_CHOICES_LIMIT)
        measures_by_model: dict[str, list[dict[str, str]] | None] = {}
        choices = []
        for favourite in favourites:
            model_name = favourite.model_id
            if model_name not in measures_by_model:
                measures_by_model[model_name] = self._metric_measures_of(model_name)
            measures = measures_by_model[model_name]
            if measures is None or self._metric_domain(favourite) is None:
                continue
            choices.append(
                {
                    "id": favourite.id,
                    "name": favourite.name,
                    "model_name": self.env["ir.model"]._get(model_name).name,
                    "measures": measures,
                }
            )
        return choices

    @api.model
    def _metric_measures_of(self, model_name: str) -> list[dict[str, str]] | None:
        if model_name not in self.env or not self.env[model_name].has_access("read"):
            return None
        model = self.env[model_name]
        measures = [
            {"name": name, "label": field.get_description(self.env)["string"]}
            for name, field in model._fields.items()
            if field.type in METRIC_FIELD_TYPES
            and field.store
            and field.aggregator
            and name != "id"
            and model._has_field_access(field, "read")
        ]
        return [{"name": "__count", "label": self.env._("Records")}] + sorted(
            measures, key=lambda measure: measure["label"]
        )
