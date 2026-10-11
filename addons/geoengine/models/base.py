import logging
from typing import TYPE_CHECKING, Any

from lxml import etree
from markupsafe import Markup

from odoo import api, models
from odoo.exceptions import MissingError, UserError
from odoo.models import parse_read_group_spec
from odoo.tools import SQL

from .fields import GEO_AGGREGATES, GeoField, _get_transformer, geo_aggregate_sql
from .geo_types import DEFAULT_SRID, parse_epsg_code, parse_extent
from .geometry_check import find_geometry_problem
from .geometry_edit import edit_shape, merge_shapes, split_shape
from .projections import projection_definitions
from .static_map import MapItem, MapStyle, render_static_map
from odoo.addons.base.models.ir_ui_view import IrUiView

if TYPE_CHECKING:
    from .geoengine_vector_layer import GeoVectorLayer

logger = logging.getLogger(__name__)

_VECTOR_LAYER_FIELDS = [
    "active_on_startup",
    "begin_color",
    "classification",
    "cluster_distance",
    "cluster_min_distance",
    "display_polygon_labels",
    "end_color",
    "geo_repr",
    "heatmap_blur",
    "heatmap_radius",
    "layer_opacity",
    "max_size",
    "min_size",
    "model_domain",
    "name",
    "nb_class",
    "readonly",
    "render_engine",
    "sequence",
    "webgl_threshold",
]
_RASTER_LAYER_FIELDS = [
    "attribution",
    "format_suffix",
    "matrix_set",
    "max_extent",
    "max_zoom",
    "name",
    "opacity",
    "overlay",
    "params",
    "params_wms",
    "projection",
    "raster_type",
    "request_encoding",
    "resolutions",
    "server_type",
    "url",
    "wmts_layer",
]

COUNTRY_EXTENTS = {
    "AR": "-8236103.069, -6701835.442, -6176933.388, -2482050.358",
    "AU": "12523443.650, -5425372.874, 17718594.626, -1002809.810",
    "BR": "-8238295.906, -3958058.731, -3817351.773, 596701.739",
    "CA": "-16701843.534, 4945270.895, -5274207.481, 10012706.856",
    "CN": "8033424.854, 2062203.412, 15028131.258, 7033392.879",
    "DE": "602300.693, 5906033.914, 1676928.850, 7362466.924",
    "ES": "-2037508.343, 3874226.918, 470912.435, 5635549.221",
    "FR": "-623476.683, 5009377.086, 1194763.021, 6636950.717",
    "GB": "-1393916.857, 6430683.307, 196849.538, 8067205.739",
    "IN": "7699217.231, 804089.846, 10826004.171, 4439651.527",
    "IT": "694181.106, 4359495.416, 2100336.319, 5958418.618",
    "JP": "13845283.274, 3422486.531, 15916789.904, 5472679.656",
    "MX": "-13173896.503, 1632778.928, -9633272.717, 3910375.796",
    "US": "-14764617.394, 2273030.926, -6679169.448, 7074326.998",
}

EXTENT_DENSIFY_POINTS = 21

DEFAULT_EXTENT = "-123164.85222423, 5574694.9538936, 1578017.6490538, 6186191.1800898"


def _notification(message: str) -> dict[str, Any]:
    return {
        "type": "ir.actions.client",
        "tag": "display_notification",
        "params": {"message": message, "type": "success", "sticky": False},
    }


class Base(models.AbstractModel):
    _inherit = "base"

    def _read_group_select(self, aggregate_spec: str, query) -> SQL:
        if aggregate_spec != "__count":
            fname, _property_name, func = parse_read_group_spec(aggregate_spec)
            if func in GEO_AGGREGATES:
                field = self._fields.get(fname)
                if not isinstance(field, GeoField):
                    what = f"is {field.type!r}" if field else "does not exist"
                    raise ValueError(
                        f"Spatial aggregate {func!r} can only be used on "
                        f"geometry fields, but {self._name}.{fname} {what}."
                    )
                self._check_field_access(field, "read")
                return geo_aggregate_sql(
                    func, self._field_to_sql(self._table, fname, query), field.srid
                )
        return super()._read_group_select(aggregate_spec, query)

    @api.model
    def _get_view_field_attributes(self) -> list[str]:
        return [*super()._get_view_field_attributes(), "geo_type", "srid", "dim"]

    @api.model
    def _get_default_map_extent(self, view: IrUiView | None = None) -> str:
        if view and (extent := view._map_settings().default_map_extent):
            return extent

        if system_extent := self.env.registry.settings.get(
            self.env, "geoengine.default_map_extent", default=False
        ):
            return system_extent

        if (country_code := self.env.company.country_id.code) and (
            extent := COUNTRY_EXTENTS.get(country_code.upper())
        ):
            return extent

        return DEFAULT_EXTENT

    @api.model
    def _extent_in_projection(self, extent: str | bool, projection: str) -> str | bool:
        if not extent:
            return extent
        if (srid := parse_epsg_code(projection)) is None:
            logger.warning(
                "Ignoring unusable map projection %r; extent left unprojected.",
                projection,
            )
            return extent
        if srid == DEFAULT_SRID:
            return extent
        if (corners := parse_extent(extent)) is None:
            logger.warning(
                "Ignoring malformed map extent %r; expected "
                "'min_x, min_y, max_x, max_y'.",
                extent,
            )
            return extent
        bounds = _get_transformer(DEFAULT_SRID, srid).transform_bounds(
            *corners, densify_pts=EXTENT_DENSIFY_POINTS
        )
        return ", ".join(f"{value:.6f}" for value in bounds)

    @api.model
    def _get_geo_view(self, view_id: int | None = None) -> IrUiView:
        views = self.env["ir.ui.view"].sudo()

        if view_id:
            view = views.browse(view_id).exists()
            if view.type == "geoengine" and view.model == self._name:
                return view
            raise MissingError(
                self.env._(
                    "View %(view_id)s is not a geoengine view of %(model)s.",
                    view_id=view_id,
                    model=self._name,
                )
            )

        if not (view_id := views.default_view(self._name, "geoengine")):
            raise MissingError(
                self.env._(
                    "No geoengine view defined for the model %s.\nPlease create a view or modify view mode.",
                )
                % self._name,
            )

        return views.browse(view_id)

    def _geo_static_map(
        self,
        field_names: str | list[str] | None = None,
        style: MapStyle | None = None,
        **options: Any,
    ) -> Markup | None:
        if isinstance(field_names, str):
            field_names = [field_names]
        fields = [
            self._fields[name]
            for name in field_names
            or [
                name
                for name, field in self._fields.items()
                if isinstance(field, GeoField) and field.store
            ]
        ]
        fields = [field for field in fields if self._has_field_access(field, "read")]
        items = [
            MapItem(record[field.name], field.srid, style or MapStyle())
            for record in self
            for field in fields
            if record[field.name]
        ]
        return render_static_map(self.env, items, **options)

    @api.model
    def get_layers(self, view_id: int | None = None) -> dict[str, Any]:
        self.check_access("read")
        view = self._get_geo_view(view_id)
        settings = view._map_settings()
        projection = settings.projection

        if not (validation := self._check_geo_view_configuration(view))["valid"]:
            logger.warning(
                "Geoengine view '%s' has configuration errors: %s",
                view.name,
                ", ".join(validation["errors"]),
            )

        return {
            "backgrounds": view.raster_layer_ids.read(_RASTER_LAYER_FIELDS),
            "actives": self._vector_layer_payload(view),
            "projection": projection,
            "projections": projection_definitions(
                self.env,
                [projection, *view.raster_layer_ids.mapped("projection")],
            ),
            "default_map_extent": self._extent_in_projection(
                self._get_default_map_extent(view), projection
            ),
            "restricted_extent": self._extent_in_projection(
                settings.restricted_extent, projection
            ),
            "default_map_zoom": settings.default_map_zoom,
            "render_engine": settings.render_engine or "auto",
            "webgl_threshold": settings.webgl_threshold or 1000,
            "controls": {
                "attribution": settings.show_attribution,
                "fullscreen": settings.show_fullscreen,
                "mouse_position": settings.show_mouse_position,
                "overview_map": settings.show_overview_map,
                "zoom_slider": settings.show_zoom_slider,
            },
            "validation": validation,
        }

    @api.model
    def get_geometry_problem(
        self, field_name: str, value: str
    ) -> dict[str, Any] | None:
        self.check_access("read")
        field = self._geo_field(field_name)
        if not (problem := find_geometry_problem(field, value, self)):
            return None
        return {"message": problem.message, "location": problem.location}

    @api.model
    def get_edited_shape(
        self, field_name: str, value: str, sketch: str, edit: str
    ) -> str:
        self.check_access("read")
        field = self._geo_field(field_name)
        return edit_shape(field, value, sketch, edit, self)

    def _geo_field(self, field_name: str) -> GeoField:
        field = self._fields.get(field_name)
        if not isinstance(field, GeoField):
            raise ValueError(f"{self._name}.{field_name} is not a geometry field")
        return field

    def action_split_shape(self, field_name: str, line: str) -> dict[str, Any]:
        self.check_singleton()
        field = self._geo_field(field_name)
        if not self[field_name]:
            raise UserError(self.env._("This record has no shape to split."))
        kept, pieces = split_shape(field, self[field_name], line, self)
        self[field_name] = kept
        for piece in pieces:
            self.copy({field_name: piece})
        return _notification(
            self.env._("The shape is now %(count)d records.", count=len(pieces) + 1)
        )

    def action_merge_shapes(self, field_name: str) -> dict[str, Any]:
        field = self._geo_field(field_name)
        if len(self) < 2:
            raise UserError(self.env._("Select two or more shapes to merge."))
        if "active" not in self._fields:
            raise UserError(
                self.env._(
                    "%(model)s records cannot be archived, so their shapes are not "
                    "merged into one.",
                    model=self._description,
                )
            )
        survivor, merged = self[0], self[1:]
        survivor[field.name] = merge_shapes(
            [record[field.name] for record in self if record[field.name]]
        )
        merged.action_archive()
        return _notification(
            self.env._(
                "%(count)d shapes are merged into %(name)s; the others are archived.",
                count=len(self),
                name=survivor.display_name,
            )
        )

    @api.model
    def _vector_layer_payload(self, view: IrUiView) -> list[dict[str, Any]]:
        layers = view.vector_layer_ids
        referenced = (
            layers.geo_field_id
            | layers.attribute_field_id
            | layers.color_field_id
            | layers.heatmap_weight_field_id
        )
        referenced.fetch(["name"])
        layers.model_id.fetch(["model"])
        return [
            row
            | {
                "geo_field_name": layer.geo_field_id.name or False,
                "attribute_field_name": layer.attribute_field_id.name or False,
                "color_field_name": layer.color_field_id.name or False,
                "heatmap_weight_field_name": layer.heatmap_weight_field_id.name
                or False,
                "resModel": layer._name,
                "resId": layer.id,
                "domain": layer._map_domain(),
                "model": layer.model_id.model or view.model,
            }
            for layer, row in zip(
                layers, layers.read(_VECTOR_LAYER_FIELDS), strict=True
            )
        ]

    def _check_geo_view_configuration(self, view: IrUiView) -> dict[str, Any]:
        errors = []
        warnings = []

        if not view.raster_layer_ids:
            errors.append(
                self.env._(
                    "No raster layers configured. At least one raster layer "
                    "(e.g., OpenStreetMap) is required for map background."
                ),
            )

        if not view.vector_layer_ids:
            errors.append(
                self.env._(
                    "No vector layers configured. At least one vector layer is required to display data on the map."
                ),
            )
        else:
            foreign_models = {
                model
                for layer in view.vector_layer_ids
                if (model := layer.model_id.sudo().model) and model != view.model
            }
            models_with_geo_view = (
                {
                    model
                    for [model] in self.env["ir.ui.view"]
                    .sudo()
                    ._read_group(
                        [
                            ("model", "in", list(foreign_models)),
                            ("type", "=", "geoengine"),
                            ("mode", "=", "primary"),
                        ],
                        ["model"],
                    )
                }
                if foreign_models
                else set()
            )
            for layer in view.vector_layer_ids:
                self._check_vector_layer(layer, view, errors, models_with_geo_view)

        if not etree.fromstring(view.arch.encode("utf-8")).xpath(
            '//templates/t[@t-name="info_box"]',
        ):
            warnings.append(
                self.env._(
                    "No info_box template defined. Popup information "
                    "will not be displayed when clicking on map features."
                ),
            )

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        }

    @api.model
    def _check_vector_layer(
        self,
        layer: GeoVectorLayer,
        view: IrUiView,
        errors: list[str],
        models_with_geo_view: set[str],
    ) -> None:
        if not layer.geo_field_id:
            errors.append(
                self.env._("Vector layer '%s' is missing geometry field configuration.")
                % layer.name,
            )

        if not layer.model_id and not view.model:
            errors.append(
                self.env._(
                    "Vector layer '%s' has no model configured and view has no model."
                )
                % layer.name,
            )

        layer_model = layer.model_id.sudo().model
        if layer.model_id and layer_model != view.model:
            if layer_model not in models_with_geo_view:
                errors.append(
                    self.env._(
                        "Vector layer '%(layer)s' reads %(model)s, which has no "
                        "geoengine view. The map cannot load another model's "
                        "records without one, so this layer will not be drawn. "
                        "Create a geoengine view for %(model)s.",
                        layer=layer.name,
                        model=layer_model,
                    ),
                )
