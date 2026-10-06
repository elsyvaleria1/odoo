from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .geo_types import parse_epsg_code, parse_extent
from .projections import is_drawable_projection

MAX_MAP_ZOOM = 21


class GeoengineViewSettings(models.Model):
    _name = "geoengine.view.settings"
    _description = "Map settings of a geoengine view"
    _rec_name = "view_id"

    view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        index=True,
        required=True,
        domain=[("type", "=", "geoengine")],
        ondelete="cascade",
    )
    projection = fields.Char(default="EPSG:3857")
    default_map_extent = fields.Char(
        help="Map extent in format: min_x, min_y, max_x, max_y (Web Mercator EPSG:3857). "
        "Leave empty to use automatic detection based on system/company settings."
    )
    restricted_extent = fields.Char(
        help="Limits map panning/zooming to this extent. Format: min_x, min_y, max_x, max_y (Web Mercator EPSG:3857). "
        "Leave empty for unrestricted navigation."
    )
    default_map_zoom = fields.Integer(
        help="Initial zoom level for the map. Range: 0 (world view) to 21 (street level). "
        "Common values: 2-4 (country), 5-8 (region/state), 9-12 (city), 13-16 (neighborhood), 17+ (building/street)."
    )
    render_engine = fields.Selection(
        selection=[
            ("auto", "Auto (recommended)"),
            ("webgl", "WebGL (best performance)"),
            ("canvas", "Canvas (editing)"),
        ],
        default="auto",
        help="Default rendering engine for all layers in this view.\n"
        "Auto: Automatically selects based on feature count and requirements.\n"
        "WebGL: GPU-accelerated, best for large datasets (>1000 features). "
        "Draws labels too, since OpenLayers 10.10.\n"
        "Canvas: required for on-map geometry editing.",
    )
    webgl_threshold = fields.Integer(
        default=1000,
        help="Feature count above which 'Auto' mode switches to WebGL rendering. "
        "Lower values = more aggressive WebGL usage (better performance). "
        "Higher values = more Canvas usage (better compatibility).",
    )
    show_attribution = fields.Boolean(
        default=True,
        help="Show data-source credits on the map. OpenStreetMap, Esri and "
        "CARTO all require attribution to be displayed, so turn this off only "
        "for a map whose sources do not.",
    )
    show_fullscreen = fields.Boolean(
        default=True,
        help="Show a button that expands the map to the full screen.",
    )
    show_mouse_position = fields.Boolean(
        help="Show the coordinates under the pointer, in the view projection."
    )
    show_overview_map = fields.Boolean(help="Show a small locator map in the corner.")
    show_zoom_slider = fields.Boolean(
        help="Show a zoom slider beside the zoom buttons."
    )

    _view_unique = models.Constraint(
        "UNIQUE(view_id)",
        "A geoengine view has one set of map settings.",
    )

    @api.constrains("view_id")
    def _check_view_is_a_map(self) -> None:
        for settings in self:
            if settings.view_id.type != "geoengine":
                raise ValidationError(
                    self.env._(
                        "Map settings belong to a geoengine view; '%(view)s' is a "
                        "%(type)s view.",
                        view=settings.view_id.name,
                        type=settings.view_id.type,
                    )
                )

    @api.constrains("default_map_extent", "restricted_extent")
    def _check_map_extents(self) -> None:
        for settings in self:
            for fname in ("default_map_extent", "restricted_extent"):
                if not (raw := settings[fname]):
                    continue
                if parse_extent(raw) is None:
                    raise ValidationError(
                        self.env._(
                            "%(field)s must be four comma-separated numbers "
                            "'min_x, min_y, max_x, max_y', with min_x/min_y "
                            "smaller than max_x/max_y. Got: %(value)s",
                            field=self._fields[fname].string or fname,
                            value=raw,
                        )
                    )

    @api.constrains("projection")
    def _check_projection(self) -> None:
        for settings in self:
            if not (raw := settings.projection):
                continue
            if (srid := parse_epsg_code(raw)) is None:
                raise ValidationError(
                    self.env._(
                        "Projection must be written 'EPSG:<code>', e.g. "
                        "EPSG:3857. Got: %(value)s",
                        value=raw,
                    )
                )
            if not is_drawable_projection(self.env, srid):
                raise ValidationError(
                    self.env._(
                        "%(value)s is not a coordinate system the map can draw: "
                        "PostGIS has no EPSG definition for it.",
                        value=raw,
                    )
                )

    @api.constrains("default_map_zoom", "webgl_threshold")
    def _check_map_numbers(self) -> None:
        for settings in self:
            if not 0 <= settings.default_map_zoom <= MAX_MAP_ZOOM:
                raise ValidationError(
                    self.env._(
                        "Initial zoom must be between 0 (world) and "
                        "%(maximum)d (street level). Got: %(value)d",
                        maximum=MAX_MAP_ZOOM,
                        value=settings.default_map_zoom,
                    )
                )
            if settings.webgl_threshold < 0:
                raise ValidationError(
                    self.env._(
                        "The WebGL threshold is a feature count and cannot be "
                        "negative. Got: %(value)d",
                        value=settings.webgl_threshold,
                    )
                )
