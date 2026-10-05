from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL
from odoo.tools.translate import html_translate

_debug = DebugLog(__name__)


class ResourceResource(models.Model):
    _inherit = "resource.resource"
    # a thing's vendor is one of its company's
    _check_company_auto = True

    asset_id = fields.One2one(
        comodel_name="resource.asset",
        inverse_name="resource_id",
        context={"active_test": False},
    )
    # what a thing is and where it came from, on the resource it is
    kind_id = fields.Many2one(
        comodel_name="resource.kind",
        index="btree_not_null",
        ondelete="restrict",
    )
    kind_code = fields.Char(related="kind_id.code")
    properties = fields.Properties(
        definition="kind_id.properties_definition",
        copy=True,
    )
    description = fields.Html(translate=html_translate)
    model = fields.Char(string="Model Name")
    model_year = fields.Integer(
        help="The commercial model year, which may differ from the year it was built.",
    )
    brand_new = fields.Boolean(default=True)
    vendor_id = fields.Many2one(
        comodel_name="res.partner",
        index="btree_not_null",
        check_company=True,
        tracking=True,
    )
    vendor_ref = fields.Char(string="Vendor Reference")
    warranty_date = fields.Date(string="Warranty Expiration Date")
    address_id = fields.Many2one(
        comodel_name="res.partner",
        string="Location",
        help="Where the resource normally is, when no inventory location tracks it.",
    )
    # a thing's odometer: the newest reading of its odometer meter
    odometer = fields.Float(
        compute="_compute_odometer",
        inverse="_inverse_odometer",
        store=True,
        readonly=False,
    )
    odometer_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        tracking=True,
        help="Unit of measurement for the odometer readings",
    )
    odometer_uom_name = fields.Char(
        related="odometer_uom_id.display_name",
        string="Odometer Unit",
    )
    odometer_meter_id = fields.Many2one(
        comodel_name="resource.meter",
        compute="_compute_odometer_meter_id",
        store=True,
    )

    def _track_prepare(self, fields_iter):
        # an asset's history is its chatter's; a person's or an intangible's
        # resource keeps none
        return super(ResourceResource, self.filtered("asset_id"))._track_prepare(
            fields_iter
        )

    @api.depends("meter_ids.kind")
    def _compute_odometer_meter_id(self) -> None:
        for resource in self:
            resource.odometer_meter_id = resource.meter_ids.filtered(
                lambda m: m.kind == "odometer"
            )[:1]

    @api.depends("odometer_meter_id.last_reading_id.value")
    def _compute_odometer(self) -> None:
        for resource in self:
            resource.odometer = resource.odometer_meter_id.value

    def _inverse_odometer(self) -> None:
        for resource in self:
            meter = resource.odometer_meter_id
            if not resource.odometer and not meter:
                continue
            if not meter:
                meter = resource._create_odometer_meter()
            if meter.value > resource.odometer:
                _debug.logic(
                    "odometer.refused", reason="below_last_reading", resource=resource
                )
                raise ValidationError(
                    self.env._(
                        "%(asset)s: the odometer cannot go below its last reading of %(value)s.",
                        asset=resource.display_name,
                        value=meter.value,
                    )
                )
            if meter.value != resource.odometer:
                meter.record(resource.odometer)

    def _create_odometer_meter(self):
        self.check_singleton()
        meter = self.env["resource.meter"].create(
            {
                "resource_id": self.id,
                "name": self.env._("Odometer"),
                "kind": "odometer",
                "uom_id": self.odometer_uom_id.id,
            }
        )
        self.invalidate_recordset(["odometer_meter_id"])
        return meter

    def _check_odometer_uom_is_not_reinterpreted(self, new_uom_id) -> None:
        """Every reading the meter holds is a number in the asset's unit, and
        nothing stores which unit it was taken in. Changing the unit therefore
        restates the whole history rather than converting it."""
        changing = self.filtered(
            lambda resource: resource.odometer_uom_id.id != new_uom_id
        )
        with_readings = changing.sudo().filtered(
            lambda resource: resource.odometer_meter_id.reading_ids
        )
        if with_readings:
            _debug.logic(
                "odometer_uom.refused", reason="readings_exist", resources=self
            )
            raise ValidationError(
                self.env._(
                    "%(assets)s already carry odometer readings in their current "
                    "unit. Changing it now would restate every one of them; "
                    "convert the readings deliberately instead.",
                    assets=", ".join(with_readings.mapped("display_name")),
                )
            )

    @api.constrains("kind_id")
    def _check_an_asset_has_a_kind(self) -> None:
        if self.filtered(lambda resource: resource.asset_id and not resource.kind_id):
            raise ValidationError(self.env._("An asset has a kind."))

    def write(self, vals):
        if "kind_id" in vals and (assets := self.asset_id):
            # a kind decides the table an asset's row lives in
            assets._check_kind_stays_in_this_table(vals["kind_id"])
        if "odometer_uom_id" in vals:
            self._check_odometer_uom_is_not_reinterpreted(vals["odometer_uom_id"])
        return super().write(vals)

    def _check_transition(self, state):
        super()._check_transition(state)
        self.asset_id._check_transition(state)

    def _check_reactivation(self):
        super()._check_reactivation()
        self.asset_id._check_reactivation()

    def _on_custody_changed(self, role, changes, planned=False):
        super()._on_custody_changed(role, changes, planned=planned)
        self.asset_id._on_custody_changed(role, changes, planned=planned)

    @api.model
    def _asset_projection_sql(self, resource_id):
        assets = self.env["resource.asset"].with_context(active_test=False)._search([])
        return SQL(
            "(SELECT asset.id FROM resource_asset asset WHERE asset.resource_id = %s AND asset.id IN %s)",
            resource_id,
            assets.subselect(),
        )
