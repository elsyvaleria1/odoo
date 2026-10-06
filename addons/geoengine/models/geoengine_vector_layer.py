import base64
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Domain
from odoo.models import BaseModel
from odoo.tools import SQL

from .fields import GeoField
from .geo_domain import parse_domain_text
from .geo_types import GEO_FIELD_TTYPES, POINT_TTYPES
from .vector_tiles import (
    Cell,
    HeatView,
    Tile,
    cell_records_query,
    extent_sql,
    fetch_within_budget,
    heat_cells_sql,
    render_tile,
    tile_sql,
)

_logger = logging.getLogger(__name__)


MAX_CLASS_VALUES = 100_000

CELL_RECORD_LIMIT = 80

ACTIVE_IDS_PLACEHOLDER = "{ACTIVE_IDS}"


def _contains_active_ids(node) -> bool:
    if isinstance(node, str):
        return ACTIVE_IDS_PLACEHOLDER in node
    if isinstance(node, dict):
        return any(_contains_active_ids(value) for value in node.values())
    if isinstance(node, (list, tuple)):
        return any(_contains_active_ids(item) for item in node)
    return False


SUPPORTED_ATT = [
    "float",
    "integer",
    "date",
    "datetime",
    "char",
    "text",
    "selection",
]

NUMBER_ATT = ["float", "integer"]

POINT_ONLY_REPR = ("heatmap", "cluster")


class GeoVectorLayer(models.Model):
    _name = "geoengine.vector.layer"
    _inherit = ["mixin.color"]
    _description = "Vector Layer"
    _order = "sequence ASC, name"

    name = fields.Char(
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=6)
    geo_repr = fields.Selection(
        selection=[
            ("basic", "Basic"),
            ("proportion", "Proportional Symbol"),
            ("colored", "Colored range/Chroma.js"),
            ("colored_field", "Color from Field"),
            ("heatmap", "Heatmap"),
            ("cluster", "Clustered Points"),
        ],
        required=True,
        help="Basic: Single color for all features.\n"
        "Proportional Symbol: Size based on numeric attribute.\n"
        "Colored range: Color gradient based on classification.\n"
        "Color from Field: Read hex color directly from a Char field.\n"
        "Heatmap: Density surface. Point geometry only.\n"
        "Clustered Points: Nearby points collapse into one counted marker. "
        "Point geometry only.",
    )
    heatmap_radius = fields.Integer(
        default=8,
        help="Radius of each point's contribution, in pixels.",
    )
    heatmap_blur = fields.Integer(
        default=15,
        help="Blur applied to the density surface, in pixels. Larger values "
        "smooth the result; smaller ones keep individual points distinct.",
    )
    heatmap_weight_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        string="Weight Field",
        help="Numeric field weighting each point's contribution. Values are "
        "normalised against the layer's maximum, so the field's unit does not "
        "matter. Leave empty to weight every point equally.",
    )
    cluster_distance = fields.Integer(
        default=40,
        help="Distance in pixels within which points are clustered together.",
    )
    cluster_min_distance = fields.Integer(
        default=20,
        help="Minimum distance in pixels between two cluster markers. Keeps "
        "clusters from overlapping as you zoom. Must not exceed the "
        "clustering distance.",
    )
    classification = fields.Selection(
        selection=[
            ("unique", "Unique value"),
            ("interval", "Interval"),
            ("quantile", "Quantile"),
        ],
        required=False,
    )
    begin_color = fields.Char(
        required=False,
        help="hex value",
    )
    end_color = fields.Char(
        default="#FF680A",
        required=False,
        help="hex value",
    )
    nb_class = fields.Integer(
        default=1,
        help="Number of classification categories for data visualization",
    )
    nb_class_recommended = fields.Integer(
        compute="_compute_nb_class_recommended",
        store=False,
        help="Maximum number of classes based on distinct values in your data",
    )
    model_id = fields.Many2one(
        comodel_name="ir.model",
        compute="_compute_model_id",
        store=True,
        readonly=False,
    )
    model_name = fields.Char(
        string="Technical Name",
        compute="_compute_model_name",
    )
    model_domain = fields.Char(default="[]")
    model_view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        compute="_compute_model_view_id",
        domain=[("type", "=", "geoengine")],
    )
    view_id = fields.Many2one(
        comodel_name="ir.ui.view",
        index=True,
        required=True,
        domain=[("type", "=", "geoengine")],
    )
    geo_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        required=True,
        domain=[("ttype", "in", list(GEO_FIELD_TTYPES))],
        ondelete="cascade",
    )
    attribute_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        domain=[("ttype", "in", SUPPORTED_ATT)],
        help="Field used for classification in colored/proportional modes.",
    )
    color_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        domain=[("ttype", "in", ["char", "text"])],
        help="Char field containing hex color values (e.g., '#FF5733') for 'Color from Field' mode.",
    )
    readonly = fields.Boolean()
    display_polygon_labels = fields.Boolean()
    active_on_startup = fields.Boolean(
        help="Layer will be shown on startup if checked."
    )
    layer_opacity = fields.Float(
        default=1.0,
        help="Layer transparency (0=transparent, 1=opaque)",
    )
    min_size = fields.Integer(
        default=5,
        help="Radius in pixels for the smallest value, in 'Proportional Symbol' mode.",
    )
    max_size = fields.Integer(
        default=15,
        help="Radius in pixels for the largest value, in 'Proportional Symbol' mode.",
    )
    webgl_threshold = fields.Integer(
        help="Feature count above which 'Auto' switches this layer to WebGL. "
        "Leave at 0 to use the view's threshold."
    )
    render_engine = fields.Selection(
        selection=[
            ("inherit", "Use View Default"),
            ("auto", "Auto"),
            ("webgl", "WebGL"),
            ("canvas", "Canvas"),
        ],
        default="inherit",
        help="Override the view's default render engine for this layer only.\n"
        "'Use View Default' inherits from the parent geoengine view.\n"
        "Auto: Automatically selects based on feature count.\n"
        "WebGL: GPU-accelerated, best for large datasets. Draws labels too.\n"
        "Canvas: required for on-map geometry editing.",
    )

    _opacity_range = models.Constraint(
        "CHECK(layer_opacity >= 0 AND layer_opacity <= 1)",
        "Layer opacity must be between 0 and 1",
    )
    _sequence_positive = models.Constraint(
        "CHECK(sequence >= 0)",
        "Sequence must be positive",
    )
    _nb_class_positive = models.Constraint(
        "CHECK(nb_class >= 1)",
        "Number of classes must be at least 1",
    )
    _symbol_sizes_sane = models.Constraint(
        "CHECK(min_size >= 0 AND max_size >= min_size)",
        "Maximum symbol size must be greater than or equal to the minimum, "
        "and neither can be negative",
    )
    _webgl_threshold_positive = models.Constraint(
        "CHECK(webgl_threshold >= 0)",
        "The WebGL threshold is a feature count and cannot be negative",
    )

    @api.constrains("geo_field_id", "model_id")
    def _check_geo_field_id(self) -> None:
        for rec in self:
            if rec.model_id and rec.geo_field_id:
                if rec.geo_field_id.model_id != rec.model_id:
                    raise ValidationError(
                        self.env._(
                            "The geo_field_id must be a field in %s model",
                            rec.model_id.display_name,
                        ),
                    )

    @api.constrains("geo_repr", "attribute_field_id", "classification")
    def _check_geo_repr(self) -> None:
        for rec in self:
            needs_attribute = rec.geo_repr in ("colored", "proportion")
            if needs_attribute and not rec.attribute_field_id:
                raise ValidationError(
                    self.env._(
                        "The '%(repr)s' representation needs an attribute field "
                        "to read its values from.",
                        repr=dict(self._fields["geo_repr"].selection)[rec.geo_repr],
                    ),
                )
            if (
                rec.attribute_field_id
                and rec.attribute_field_id.ttype not in NUMBER_ATT
            ):
                if (
                    rec.geo_repr == "colored" and rec.classification != "unique"
                ) or rec.geo_repr == "proportion":
                    raise ValidationError(
                        self.env._(
                            "Field '%(field)s' is a %(type)s. Interval and "
                            "quantile classification, and proportional symbols, "
                            "need a numeric field.",
                            field=rec.attribute_field_id.name,
                            type=rec.attribute_field_id.ttype,
                        ),
                    )

    @api.constrains(
        "geo_field_id",
        "attribute_field_id",
        "color_field_id",
        "heatmap_weight_field_id",
    )
    def _check_fields_belong_to_the_drawn_model(self) -> None:
        for rec in self:
            if not rec.geo_field_id:
                continue
            for fname in (
                "attribute_field_id",
                "color_field_id",
                "heatmap_weight_field_id",
            ):
                field = rec[fname]
                if field and field.model != rec.geo_field_id.model:
                    raise ValidationError(
                        self.env._(
                            "%(label)s '%(field)s' is a field of %(other)s, but the "
                            "layer draws %(model)s.",
                            label=self._fields[fname].string,
                            field=field.name,
                            other=field.model,
                            model=rec.geo_field_id.model,
                        ),
                    )

    @api.constrains("geo_repr", "color_field_id")
    def _check_color_field(self) -> None:
        for rec in self:
            if rec.geo_repr == "colored_field" and not rec.color_field_id:
                raise ValidationError(
                    self.env._(
                        "Color field is required for 'Color from Field' representation mode."
                    ),
                )

    @api.constrains("geo_repr", "geo_field_id")
    def _check_point_only_repr(self) -> None:
        for rec in self:
            if rec.geo_repr not in POINT_ONLY_REPR or not rec.geo_field_id:
                continue
            if rec.geo_field_id.ttype not in POINT_TTYPES:
                raise ValidationError(
                    self.env._(
                        "The '%(repr)s' representation needs point geometry, but "
                        "'%(field)s' is a %(type)s. OpenLayers would draw an "
                        "empty layer without reporting an error.",
                        repr=dict(self._fields["geo_repr"].selection)[rec.geo_repr],
                        field=rec.geo_field_id.name,
                        type=rec.geo_field_id.ttype,
                    ),
                )

    @api.constrains("geo_repr", "heatmap_weight_field_id", "geo_field_id")
    def _check_heatmap_weight_field(self) -> None:
        for rec in self:
            weight = rec.heatmap_weight_field_id
            if not weight:
                continue
            if weight.ttype not in NUMBER_ATT:
                raise ValidationError(
                    self.env._(
                        "Heatmap weight field '%(field)s' is a %(type)s. "
                        "Weighting needs a numeric field.",
                        field=weight.name,
                        type=weight.ttype,
                    ),
                )

    @api.constrains("cluster_distance", "cluster_min_distance")
    def _check_cluster_distances(self) -> None:
        for rec in self:
            if rec.cluster_distance < 0 or rec.cluster_min_distance < 0:
                raise ValidationError(
                    self.env._("Cluster distances cannot be negative."),
                )
            if rec.cluster_min_distance > rec.cluster_distance:
                raise ValidationError(
                    self.env._(
                        "The minimum distance between clusters (%(min)s px) "
                        "cannot exceed the clustering distance (%(dist)s px).",
                        min=rec.cluster_min_distance,
                        dist=rec.cluster_distance,
                    ),
                )

    @api.constrains("geo_repr", "heatmap_radius", "heatmap_blur")
    def _check_heatmap_sizes(self) -> None:
        for rec in self:
            if rec.geo_repr != "heatmap":
                continue
            if rec.heatmap_radius <= 0:
                raise ValidationError(
                    self.env._("Heatmap radius must be greater than zero."),
                )
            if rec.heatmap_blur < 0:
                raise ValidationError(
                    self.env._("Heatmap blur cannot be negative."),
                )

    @api.constrains("begin_color", "end_color")
    def _check_hex_colors(self) -> None:
        self._check_hex_color_fields("begin_color", "end_color")

    @api.constrains("model_domain")
    def _check_model_domain(self) -> None:
        for rec in self:
            if not rec.model_domain:
                continue
            try:
                Domain(parse_domain_text(self.env, rec.model_domain))
            except Exception as e:
                raise ValidationError(
                    self.env._(
                        "Model domain must be a valid Odoo domain "
                        "(e.g. [('field', '=', value)]). Error: %s",
                    )
                    % str(e),
                ) from e

    @api.depends("model_id")
    def _compute_model_view_id(self) -> None:
        privileged = self.with_privilege(
            "geoengine.privilege_resolve_layer_view",
            reason="a map layer finds the map view of the model it draws",
        )
        views = privileged.env["ir.ui.view"]
        default_view_of = {
            model: views.default_view(model, "geoengine")
            for model in privileged.model_id.mapped("model")
        }
        for rec, layer in zip(self, privileged, strict=True):
            rec.model_view_id = default_view_of.get(layer.model_id.model, False)

    @api.depends("model_id", "geo_field_id")
    def _compute_model_name(self) -> None:
        for rec in self:
            rec.model_name = rec._target_model_name()

    @api.depends("geo_field_id", "view_id")
    def _compute_model_id(self) -> None:
        for rec in self:
            if rec.view_id and rec.geo_field_id:
                if rec.view_id.model != rec.geo_field_id.model:
                    rec.model_id = rec.geo_field_id.model_id
                else:
                    rec.model_id = False
            else:
                rec.model_id = False

    @api.depends("attribute_field_id", "model_id", "model_domain", "geo_repr")
    def _compute_nb_class_recommended(self) -> None:
        for rec in self:
            rec.nb_class_recommended = 0

            if (
                rec.geo_repr != "colored"
                or not rec.attribute_field_id
                or not rec.model_id
            ):
                continue

            try:
                num_distinct = rec._count_distinct_values()

                if num_distinct > 0:
                    rec.nb_class_recommended = min(max(1, num_distinct - 1), 10)

            except AccessError, ValueError:
                rec.nb_class_recommended = 0

    def _attribute_target(self) -> tuple[BaseModel, str] | None:
        self.check_singleton()
        model_name = self._target_model_name()
        if not self.attribute_field_id or not model_name:
            return None
        model = self.env[model_name]
        field_name = self.sudo().attribute_field_id.name
        field = model._fields.get(field_name)
        if field is None or not field.store:
            _logger.debug(
                "Layer %s classifies by %s.%s, which is not a stored field",
                self.name,
                model_name,
                field_name,
            )
            return None
        return model, field_name

    def _population_domain(self, layer_domain: list | None) -> Domain:
        if layer_domain is None:
            return Domain(self._parsed_model_domain())
        return Domain(layer_domain)

    def _count_distinct_values(self, limit: int = 1000) -> int:
        if not (target := self._attribute_target()):
            return 0
        model, field_name = target
        spec = field_name
        if model._fields[field_name].type in ("date", "datetime"):
            spec = f"{field_name}:day"
        return len(
            model._read_group(
                self._population_domain(None), groupby=[spec], limit=limit
            )
        )

    def get_class_bounds(self, layer_domain: list | None = None) -> dict:
        """Bounds of the attribute over the layer's population.

        ``layer_domain`` is the layer's domain as the map evaluated it (its
        filter, the search, the drawn ids); without one the stored filter
        applies.
        """
        if not (target := self._attribute_target()):
            return {}
        model, field_name = target
        [[count, minimum, maximum]] = model._read_group(
            self._population_domain(layer_domain),
            aggregates=["__count", f"{field_name}:min", f"{field_name}:max"],
        )
        if not count or any(v is None or v is False for v in (minimum, maximum)):
            return {}
        return {"min": minimum, "max": maximum}

    def get_class_values(
        self,
        layer_domain: list | None = None,
        limit: int = MAX_CLASS_VALUES,
        distinct: bool = False,
    ) -> list:
        """The attribute's non-empty values over the layer's population, as
        ``get_class_bounds`` reads it, each once when ``distinct`` (all unique
        classes need); empty when there are more than ``limit``, and the map
        then classifies the drawn features."""
        if not (target := self._attribute_target()):
            return []
        model, field_name = target
        limit = min(limit or MAX_CLASS_VALUES, MAX_CLASS_VALUES)
        domain = self._population_domain(layer_domain)
        field_type = model._fields[field_name].type
        # A datetime grouped by day would not match the full timestamps the
        # map compares against, so it is read row by row like any population.
        if distinct and field_type != "datetime":
            spec = f"{field_name}:day" if field_type == "date" else field_name
            values = [
                value for [value] in model._read_group(domain, [spec], limit=limit + 1)
            ]
        else:
            values = [
                row[field_name]
                for row in model.search_read(domain, [field_name], limit=limit + 1)
            ]
        if len(values) > limit:
            _logger.debug(
                "Layer %s has more than %d values; classifying over the drawn "
                "features instead",
                self.name,
                limit,
            )
            return []
        return [value for value in values if value is not False and value is not None]

    def get_class_quantiles(
        self, layer_domain: list | None = None, nb_class: int = 0
    ) -> list[float]:
        """Quantile class bounds of the attribute over the layer's population,
        computed by the database for a population too large to send as values
        (``get_class_values``): ``nb_class + 1`` ascending bounds, or empty."""
        if not (target := self._attribute_target()):
            return []
        model, field_name = target
        nb_class = max(1, min(int(nb_class or self.nb_class or 1), 100))
        query = model._search(
            self._population_domain(layer_domain) & Domain(field_name, "!=", False)
        )
        query.order = None
        column = model._field_to_sql(query.table, field_name, query)
        fractions = [i / nb_class for i in range(nb_class + 1)]
        [[bounds]] = self.env.execute_query(
            query.select(
                SQL(
                    "percentile_cont(%s::float8[]) WITHIN GROUP (ORDER BY %s)",
                    fractions,
                    column,
                )
            )
        )
        return [float(bound) for bound in bounds or []]

    def get_tile(
        self, z: int, x: int, y: int, layer_domain: list | None = None
    ) -> dict:
        """The layer's population inside one Web Mercator tile, as a Mapbox
        vector tile (base64): a feature per record carrying its id and styled
        values or, for points, a feature per grid cell carrying its count (a
        cell of one record keeps that record's id and values). ``too_dense`` is set, and no tile returned,
        when the tile did not render within ``geoengine.tile_timeout_ms``.
        """
        self.check_singleton()
        self.check_access("read")
        tile = Tile.checked(self.env, z, x, y)
        model, field = self._tile_target()
        properties = self._tile_property_names(model)
        for name in properties:
            model._check_field_access(model._fields[name], "read")
        sql = tile_sql(
            model, field, self._population_domain(layer_domain), tile, properties
        )
        data = render_tile(self.env, sql)
        if data is None:
            return {"tile": "", "too_dense": True}
        return {"tile": base64.b64encode(data).decode(), "too_dense": False}

    def get_cell_records(
        self,
        cell: str,
        layer_domain: list | None = None,
        limit: int = CELL_RECORD_LIMIT,
    ) -> dict:
        """The records a tile counted in one cell (its ``cell`` address), for
        a map where they stack too close to be told apart by zooming:
        ``{"records": [{"id", "display_name"}], "more": bool}``."""
        self.check_singleton()
        self.check_access("read")
        model, field = self._tile_target()
        limit = max(1, min(int(limit or CELL_RECORD_LIMIT), CELL_RECORD_LIMIT))
        query = cell_records_query(
            model,
            field,
            self._population_domain(layer_domain),
            Cell.checked(self.env, cell),
        )
        query.limit = limit + 1
        records = model.browse(query.get_result_ids())
        return {
            "records": [
                {"id": record.id, "display_name": record.display_name}
                for record in records[:limit]
            ],
            "more": len(records) > limit,
        }

    def get_heat_cells(
        self, extent: list, zoom: float, layer_domain: list | None = None
    ) -> dict:
        """The layer's population in a heatmap's view, summed into cells of a
        few pixels: ``{"cells": [[x, y, weight]], "too_dense": bool}`` in Web
        Mercator, weighted by the heatmap's weight field or by count."""
        self.check_singleton()
        self.check_access("read")
        model, field = self._tile_target()
        weight_name = self.heatmap_weight_field_id.name
        weight = model._fields.get(weight_name) if weight_name else None
        if weight is not None and weight.store:
            model._check_field_access(weight, "read")
        else:
            weight_name = None
        row = fetch_within_budget(
            self.env,
            heat_cells_sql(
                model,
                field,
                self._population_domain(layer_domain),
                HeatView.checked(self.env, extent, zoom),
                weight_name,
            ),
        )
        if row is None:
            return {"cells": [], "too_dense": True}
        return {"cells": row[0], "too_dense": False}

    def get_tile_extent(self, layer_domain: list | None = None) -> list[float] | None:
        """The Web Mercator bounds of the layer's population, for framing a
        tiled layer; None when it is empty or not measured within the tile
        budget."""
        self.check_singleton()
        self.check_access("read")
        model, field = self._tile_target()
        row = fetch_within_budget(
            self.env, extent_sql(model, field, self._population_domain(layer_domain))
        )
        if row is None or row[0] is None:
            return None
        return list(row)

    def _tile_target(self) -> tuple[BaseModel, GeoField]:
        model = self.env[self._target_model_name()]
        model.check_access("read")
        field = model._fields[self.geo_field_id.name]
        model._check_field_access(field, "read")
        return model, field

    def _tile_property_names(self, model: BaseModel) -> list[str]:
        names = [
            name
            for name in (
                self.attribute_field_id.name,
                self.color_field_id.name,
                self.heatmap_weight_field_id.name,
            )
            if name and (field := model._fields.get(name)) and field.store
        ]
        return list(dict.fromkeys(names))

    def _target_model_name(self) -> str | bool:
        return self.sudo().model_id.model or self.sudo().geo_field_id.model

    def _map_domain(self) -> list | None:
        if not self.model_domain:
            return []
        try:
            return parse_domain_text(self.env, self.model_domain)
        except (SyntaxError, TypeError, ValueError) as e:
            _logger.warning(
                "Layer %s: model_domain cannot be evaluated: %s", self.name, e
            )
            return None

    def _parsed_model_domain(self) -> list:
        if not self.model_domain:
            return []
        try:
            domain = parse_domain_text(self.env, self.model_domain)
        except (SyntaxError, TypeError, ValueError) as e:
            _logger.debug("Ignoring unparseable model_domain: %s", e)
            return []

        if _contains_active_ids(domain):
            _logger.debug(
                "Layer %s has a client-side %s domain; ignoring it server-side",
                self.name,
                ACTIVE_IDS_PLACEHOLDER,
            )
            return []
        return domain
