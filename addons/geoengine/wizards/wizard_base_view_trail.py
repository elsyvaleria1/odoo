import logging
from datetime import datetime, timedelta
from itertools import starmap
from typing import Any, NamedTuple

from shapely import set_srid
from shapely.geometry import LineString

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.colors import GEO_TRAIL_COLORS, get_palette_color
from odoo.tools import SQL

from ..models.fields import fit_line_vertices, max_geometry_size, reproject
from ..models.geo_domain import parse_domain_text
from ..models.geo_types import GEO_FIELD_TTYPES

logger = logging.getLogger(__name__)

MAX_TRAIL_RECORDS = 200_000


class TrailPosition(NamedTuple):
    x: float | None
    y: float | None
    moment: datetime
    device: Any


class WizardBaseViewTrail(models.TransientModel):
    _name = "wizard.base.view.trail"
    _inherit = ["mixin.color"]
    _description = "Trail Generation Wizard"

    model_id = fields.Many2one(
        comodel_name="ir.model",
        required=True,
        help="Model containing position records (must have geo fields)",
    )
    model_name = fields.Char(
        related="model_id.model",
        string="Technical Name",
        readonly=True,
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)

        trail_model = self.env.context.get("default_trail_model")
        if trail_model and "model_id" not in res:
            model_rec = (
                self.env["ir.model"]
                .sudo()
                .search([("model", "=", trail_model)], limit=1)
            )
            if model_rec:
                res["model_id"] = model_rec.id

        return res

    date_field_id = fields.Many2one(
        comodel_name="ir.model.fields",
        domain="[('model_id', '=', model_id), ('ttype', '=', 'datetime'),"
        " ('store', '=', True)]",
        help="Datetime field to order and filter positions by. For GPS data this "
        "should be the field holding the position's own timestamp, not the "
        "record's audit dates.",
    )
    date_field = fields.Char(
        string="Date Field Name",
        compute="_compute_date_field",
        store=True,
        readonly=False,
        help="Technical name of the datetime field, taken from Date Field.",
    )

    date_from = fields.Datetime(
        default=lambda self: fields.Datetime.now() - timedelta(days=1),
        required=True,
        help="Start date for trail generation",
    )
    date_to = fields.Datetime(
        default=fields.Datetime.now,
        help="End date for trail generation (empty = now)",
    )

    group_by = fields.Selection(
        selection=[
            ("none", "Single Trail"),
            ("day", "Group by Day"),
            ("device_id", "Group by Device"),
        ],
        default="none",
        required=True,
        help="How to group positions into trail segments",
    )

    domain = fields.Char(
        default="[]",
        help="Additional filter criteria (e.g., [('status', '=', 'active')])",
    )

    trail_color = fields.Char(
        default="#0000FF",
        help="Hex color for trail line (e.g., #FF0000 for red)",
    )
    trail_width = fields.Integer(
        default=3,
        help="Line width in pixels",
    )
    trail_opacity = fields.Float(
        default=0.8,
        help="Trail transparency (0.0 = transparent, 1.0 = opaque)",
    )

    trail_ids = fields.One2many(
        comodel_name="wizard.base.view.trail.result",
        inverse_name="wizard_id",
        readonly=True,
    )
    trail_count = fields.Count(count_of="trail_ids")

    @api.depends("date_field_id")
    def _compute_date_field(self) -> None:
        for wizard in self:
            wizard.date_field = wizard.date_field_id.name or "write_date"

    @api.onchange("model_id")
    def _onchange_model_id_resets_date_field(self) -> None:
        if self.date_field_id.model_id != self.model_id:
            self.date_field_id = False

    @api.constrains("date_from", "date_to")
    def _check_dates(self) -> None:
        for wizard in self:
            if wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(self.env._("Date From must be before Date To"))

    @api.constrains("trail_color")
    def _check_trail_color(self) -> None:
        self._check_hex_color_fields("trail_color", lengths=(6,))

    @api.constrains("trail_width")
    def _check_trail_width(self) -> None:
        for wizard in self:
            if wizard.trail_width < 1 or wizard.trail_width > 20:
                raise ValidationError(
                    self.env._("Trail width must be between 1 and 20 pixels")
                )

    @api.constrains("trail_opacity")
    def _check_trail_opacity(self) -> None:
        for wizard in self:
            if wizard.trail_opacity < 0.0 or wizard.trail_opacity > 1.0:
                raise ValidationError(
                    self.env._("Trail opacity must be between 0.0 and 1.0")
                )

    def action_generate_trails(self):
        self.check_singleton()

        if not self.model_name:
            raise UserError(self.env._("Please select a model"))

        TargetModel = self.env[self.model_name]

        field = TargetModel._fields.get(self.date_field)
        if field is None or field.type != "datetime" or not field.store:
            raise UserError(
                self.env._(
                    "Date field '%(field)s' is not a stored datetime field on "
                    "model '%(model)s'. Available datetime fields: %(available)s.",
                    field=self.date_field,
                    model=self.model_name,
                    available=", ".join(
                        sorted(
                            name
                            for name, candidate in TargetModel._fields.items()
                            if candidate.type == "datetime" and candidate.store
                        )
                    )
                    or self.env._("none"),
                )
            )

        if self.group_by == "device_id" and "device_id" not in TargetModel._fields:
            raise UserError(
                self.env._(
                    "Model '%(model)s' has no device_id field, so positions "
                    "cannot be grouped by device.",
                    model=self.model_name,
                ),
            )

        geo_fields = self._get_fields_geo(TargetModel)
        if not geo_fields:
            raise UserError(
                self.env._("Model '%s' has no geo fields for trail generation")
                % self.model_name,
            )

        positions = self._trail_positions(
            TargetModel, self._get_domain_records(), geo_fields[0]
        )

        if not positions:
            raise UserError(self.env._("No records found in the specified date range"))

        if len(positions) > MAX_TRAIL_RECORDS:
            raise UserError(
                self.env._(
                    "This range covers more than %(maximum)d records. Narrow the "
                    "dates or add a filter.",
                    maximum=MAX_TRAIL_RECORDS,
                ),
            )

        logger.info(
            "Generating trails for %d records from %s to %s",
            len(positions),
            self.date_from,
            self.date_to or "now",
        )

        trails = self._generate_trails(TargetModel, positions)

        source_srid = TargetModel._fields[geo_fields[0]].srid
        trail_results = self._store_trail_results(trails, source_srid)
        return self._open_trail_map(trail_results)

    def _trail_positions(self, model, domain, geo_field) -> list[TrailPosition]:
        grouped_by_device = self.group_by == "device_id"
        used = [
            geo_field,
            self.date_field,
            *(["device_id"] if grouped_by_device else []),
        ]
        for fname in used:
            model._check_field_access(model._fields[fname], "read")
        query = model._search(
            domain, order=f"{self.date_field} ASC, id ASC", limit=MAX_TRAIL_RECORDS + 1
        )
        geometry = model._field_to_sql(model._table, geo_field, query)
        self.env.cr.execute(
            query.select(
                SQL("ST_X(ST_Centroid(%s))", geometry),
                SQL("ST_Y(ST_Centroid(%s))", geometry),
                model._field_to_sql(model._table, self.date_field, query),
                model._field_to_sql(model._table, "device_id", query)
                if grouped_by_device
                else SQL("NULL"),
            )
        )
        return list(starmap(TrailPosition, self.env.cr.fetchall()))

    def _get_fields_geo(self, model):
        points, others = [], []
        for field_name, field in model._fields.items():
            if getattr(field, "type", None) in GEO_FIELD_TTYPES and field.store:
                (points if field.type == "geo_point" else others).append(field_name)

        return points + others

    def _get_domain_records(self):
        domain = [
            (self.date_field, ">=", self.date_from),
        ]

        if self.date_to:
            domain.append((self.date_field, "<=", self.date_to))

        if self.domain and self.domain != "[]":
            try:
                extra = parse_domain_text(self.env, self.domain)
                Domain(extra)
                domain.extend(extra)
            except Exception as e:
                raise UserError(
                    self.env._("Invalid filter: %(error)s", error=str(e))
                ) from e

        return domain

    def _generate_trails(self, model, positions):
        groups: dict = {}
        if self.group_by == "day":
            for position in positions:
                day = fields.Datetime.context_timestamp(self, position.moment).date()
                groups.setdefault(day, []).append(position)
            named = {day: self.env._("Trail %(date)s", date=day) for day in groups}
        elif self.group_by == "device_id":
            for position in positions:
                if position.device:
                    groups.setdefault(position.device, []).append(position)
            named = self._device_trail_names(model, list(groups))
        else:
            groups = {None: positions}
            named = {None: self.env._("Trail %(date)s", date=self.date_from.date())}

        trails = []
        for key, group in groups.items():
            coordinates = [(p.x, p.y) for p in group if p.x is not None]
            if len(coordinates) >= 2:
                trails.append(
                    {
                        "name": named[key],
                        "geometry": LineString(coordinates),
                        "record_count": len(group),
                    }
                )
        logger.info("Generated %d trail segments", len(trails))
        return trails

    def _device_trail_names(self, model, keys) -> dict:
        field = model._fields["device_id"]
        if field.type == "many2one":
            devices = self.env[field.comodel_name].browse(keys)
            return {
                device.id: self.env._("Trail: %(device)s", device=device.display_name)
                for device in devices
            }
        return {
            key: self.env._("Trail: %(device)s", device=f"Device {key}") for key in keys
        }

    def _fit_trail(self, line: LineString, max_size: int) -> LineString:
        coords = list(line.coords)
        if (kept := fit_line_vertices(coords, max_size)) is not None:
            return LineString([coords[index] for index in kept])
        raise UserError(
            self.env._(
                "A trail of %(count)d positions is too large to draw, even "
                "simplified. Narrow the dates, or group the trail by day or device.",
                count=len(line.coords),
            )
        )

    _GROUP_PALETTE = GEO_TRAIL_COLORS

    def _color_for_trail(self, index, total):
        if total < 2 or self.group_by == "none":
            return self.trail_color
        return get_palette_color(index, self._GROUP_PALETTE, wrap=True)

    def _store_trail_results(self, trails, source_srid=4326):
        if not trails:
            return self.env["wizard.base.view.trail.result"]

        TrailResult = self.env["wizard.base.view.trail.result"]
        result_srid = TrailResult._fields["the_trail"].srid
        max_size = max_geometry_size(self.env)
        vals_list = [
            {
                "name": trail["name"],
                "the_trail": set_srid(
                    self._fit_trail(
                        reproject(trail["geometry"], source_srid, result_srid),
                        max_size,
                    ),
                    result_srid,
                ),
                "record_count": trail.get("record_count", 0),
                "wizard_id": self.id,
                "trail_color": self._color_for_trail(index, len(trails)),
                "trail_width": self.trail_width,
                "trail_opacity": self.trail_opacity,
            }
            for index, trail in enumerate(trails)
        ]
        return TrailResult.create(vals_list)

    def _open_trail_map(self, trail_results) -> dict:
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Generated Trails"),
            "res_model": "wizard.base.view.trail.result",
            "view_mode": "geoengine,list,form",
            "domain": [("id", "in", trail_results.ids)],
        }
