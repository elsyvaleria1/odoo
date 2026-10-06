import json
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.json import loads as json_loads

from .geo_types import (
    parse_epsg_code,
    parse_extent,
    parse_resolutions,
)
from .projections import is_drawable_projection

_URL_REQUIRED_TYPES = frozenset({"xyz", "wmts", "d_wms", "i_wms", "mvt"})
_URL_TYPES = _URL_REQUIRED_TYPES | {"google"}

_XYZ_TEMPLATE_TYPES = frozenset({"xyz", "mvt"})
_XYZ_PLACEHOLDERS = frozenset({"x", "y", "z"})
_PLACEHOLDER_PATTERN = re.compile(r"\{(-?\w+)\}")

_URL_PATTERN = re.compile(
    r"^("
    r"https?://[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?"
    r"|//[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?"
    r")"
    r"(:[0-9]+)?"
    r"(/.*)?$"
)


class GeoRasterLayer(models.Model):
    _name = "geoengine.raster.layer"
    _description = "Raster Layer"
    _order = "sequence ASC, name"

    view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        index=True,
        required=True,
        domain=[("type", "=", "geoengine")],
    )
    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=6)
    raster_type = fields.Selection(
        selection=[
            ("osm", "OpenStreetMap"),
            ("xyz", "XYZ Tiles"),
            ("google", "Google Maps"),
            ("wmts", "WMTS"),
            ("d_wms", "Distant WMS"),
            ("i_wms", "WMS (single image)"),
            ("mvt", "Vector Tiles (MVT)"),
        ],
        default="osm",
        required=True,
    )
    url = fields.Char()

    wmts_layer = fields.Char(
        string="WMTS layer",
        help="Identifier of the layer in the service's GetCapabilities "
        "(ows:Identifier). It is what the tile requests ask for.",
    )
    matrix_set = fields.Char(string="Matrix set")
    format_suffix = fields.Char(help="eg. png")
    request_encoding = fields.Char(help="eg. REST")
    projection = fields.Char(
        help="Tile matrix projection, e.g. EPSG:3857. Only CRS OpenLayers "
        "resolves natively work here (EPSG:4326, EPSG:3857 and the UTM zones); "
        "anything else is used untransformed and misplaces the tiles."
    )
    resolutions = fields.Char()
    max_extent = fields.Char(string="Max extent")
    params = fields.Char(help="WMTS dimension values, as a JSON object.")

    server_type = fields.Char(
        help="The type of the remote WMS server: mapserver, \
            geoserver, carmentaserver, or qgis"
    )
    params_wms = fields.Char(help="Need to provide at least a LAYERS param")

    attribution = fields.Char(
        help="Credit shown on the map for this tile source, e.g. "
        "'© OpenStreetMap contributors'. Most tile providers require it."
    )
    max_zoom = fields.Integer(
        default=20,
        help="Highest zoom level this tile source serves. Beyond it the "
        "provider returns blank tiles.",
    )

    overlay = fields.Boolean(string="Is overlay layer?")
    opacity = fields.Float(
        default=1.0,
        help="Layer transparency (0=transparent, 1=opaque)",
    )

    _opacity_range = models.Constraint(
        "CHECK(opacity >= 0 AND opacity <= 1)",
        "Opacity must be between 0 and 1",
    )
    _sequence_positive = models.Constraint(
        "CHECK(sequence >= 0)",
        "Sequence must be positive",
    )
    _max_zoom_range = models.Constraint(
        "CHECK(max_zoom >= 0 AND max_zoom <= 24)",
        "Maximum zoom must be between 0 and 24",
    )

    @api.constrains("url", "raster_type")
    def _check_url(self) -> None:
        for rec in self:
            if rec.raster_type not in _URL_TYPES:
                continue
            if not rec.url:
                if rec.raster_type in _URL_REQUIRED_TYPES:
                    raise ValidationError(
                        self.env._(
                            "A '%(type)s' layer needs a URL template.",
                            type=dict(self._fields["raster_type"].selection)[
                                rec.raster_type
                            ],
                        ),
                    )
                continue
            if not _URL_PATTERN.match(rec.url):
                raise ValidationError(
                    self.env._("'%(url)s' is not a valid URL.", url=rec.url),
                )
            placeholders = set(_PLACEHOLDER_PATTERN.findall(rec.url))
            if rec.raster_type in _XYZ_TEMPLATE_TYPES and not placeholders.issuperset(
                _XYZ_PLACEHOLDERS
            ):
                raise ValidationError(
                    self.env._(
                        "A tile URL must contain the {x}, {y} and {z} "
                        "placeholders. Got: %(url)s",
                        url=rec.url,
                    ),
                )

    @api.constrains("raster_type", "wmts_layer")
    def _check_wmts_layer(self) -> None:
        for rec in self:
            if rec.raster_type == "wmts" and not (rec.wmts_layer or "").strip():
                raise ValidationError(
                    self.env._(
                        "A WMTS layer needs the identifier of the layer to request, "
                        "as the service's GetCapabilities names it."
                    ),
                )

    @api.constrains("max_extent")
    def _check_max_extent(self) -> None:
        for layer in self:
            if layer.max_extent and parse_extent(layer.max_extent) is None:
                raise ValidationError(
                    self.env._(
                        "Max extent must be four comma-separated numbers "
                        "'min_x, min_y, max_x, max_y', with min_x/min_y smaller "
                        "than max_x/max_y. Got: %(value)s",
                        value=layer.max_extent,
                    )
                )

    @api.constrains("resolutions")
    def _check_resolutions(self) -> None:
        for layer in self:
            if layer.resolutions and parse_resolutions(layer.resolutions) is None:
                raise ValidationError(
                    self.env._(
                        "Resolutions must be a comma-separated list of positive "
                        "numbers, largest first. Got: %(value)s",
                        value=layer.resolutions,
                    )
                )

    @api.constrains("projection")
    def _check_projection(self) -> None:
        for rec in self:
            if not (raw := rec.projection):
                continue
            srid = parse_epsg_code(raw)
            if srid is None or not is_drawable_projection(self.env, srid):
                raise ValidationError(
                    self.env._(
                        "Tile projection must be written 'EPSG:<code>' and name a "
                        "coordinate system PostGIS has an EPSG definition for. "
                        "Got: %(value)s",
                        value=raw,
                    ),
                )

    @api.constrains("params")
    def _check_params_json(self) -> None:
        for rec in self:
            if rec.params:
                try:
                    json_loads(rec.params)
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValidationError(
                        self.env._("Params must be valid JSON format")
                    ) from e

    @api.constrains("params_wms", "raster_type")
    def _check_params_wms_json(self) -> None:
        for rec in self:
            if rec.raster_type not in ("d_wms", "i_wms"):
                continue
            if not rec.params_wms:
                raise ValidationError(
                    self.env._(
                        "A WMS layer needs params, including a LAYERS key, "
                        'e.g. {"LAYERS": "topp:states"}.'
                    ),
                )
            try:
                params = json_loads(rec.params_wms)
            except (json.JSONDecodeError, ValueError) as e:
                raise ValidationError(
                    self.env._("WMS params must be valid JSON.")
                ) from e
            if not isinstance(params, dict) or not any(
                key.upper() == "LAYERS" for key in params
            ):
                raise ValidationError(
                    self.env._(
                        'WMS params must include a LAYERS key, e.g. {"LAYERS": '
                        '"topp:states"}.'
                    ),
                )
