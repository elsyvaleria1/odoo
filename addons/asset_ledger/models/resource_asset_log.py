from odoo import api, fields, models
from odoo.exceptions import ValidationError


class ResourceAssetLog(models.Model):
    _inherit = "resource.asset.log"

    trace_id = fields.Many2one(  # noqa: E8529  One2many inverse of stock.lot.log_ids
        comodel_name="product.trace",
        related="asset_id.trace_id",
        store=True,
        index="btree_not_null",
    )
    date_start = fields.Date(
        string="Start Date",
        default=fields.Date.context_today,
        tracking=True,
        help="Date this entry's coverage begins",
    )
    date_end = fields.Date(
        string="End Date",
        tracking=True,
        help="Date this entry's coverage ends",
    )
    qty_fuel = fields.Float(
        string="Fuel Quantity",
        help="Quantity of fuel added to the asset, in litres.",
    )
    efficiency = fields.Float(
        compute="_compute_efficiency",
        help="Distance covered since the previous reading, per litre of fuel. The "
        "distance carries the asset's own odometer unit, so the ratio does "
        "too -- read efficiency_uom_name rather than assuming km/L.",
    )
    efficiency_uom_name = fields.Char(
        string="Efficiency Unit",
        compute="_compute_efficiency_uom_name",
    )
    days_left = fields.Integer(
        compute="_compute_days_left",
        help="Days until the end date. Negative once it has passed.",
    )

    @api.constrains("qty_fuel", "log_type")
    def _check_qty_fuel_non_negative(self) -> None:
        for log in self.filtered(lambda line: line.log_type == "fuel"):
            if log.qty_fuel < 0:
                raise ValidationError(self.env._("Fuel quantity cannot be negative."))

    @api.depends("date_end")
    def _compute_days_left(self) -> None:
        today = fields.Date.context_today(self)
        for log in self:
            log.days_left = (log.date_end - today).days if log.date_end else 0

    @api.depends("odometer_uom_name")
    def _compute_efficiency_uom_name(self) -> None:
        fuel_unit = self.env.ref("uom.product_uom_litre", raise_if_not_found=False)
        fuel_label = fuel_unit.display_name if fuel_unit else "L"
        for log in self:
            distance = log.odometer_uom_name
            log.efficiency_uom_name = f"{distance}/{fuel_label}" if distance else ""

    @api.depends("qty_fuel", "odometer", "asset_id", "date", "log_type")
    def _compute_efficiency(self) -> None:
        fuel_logs = self.filtered(
            lambda line: line.log_type == "fuel" and line.qty_fuel and line.odometer
        )
        for log in self - fuel_logs:
            log.efficiency = 0.0
        if not fuel_logs:
            return

        by_asset = fuel_logs._get_odometer_timeline()
        for log in fuel_logs:
            origin_id = log._origin.id if log._origin else 0
            previous, _next_entry = log._find_odometer_neighbours(by_asset, origin_id)
            if previous and log.odometer > previous.odometer:
                log.efficiency = (log.odometer - previous.odometer) / log.qty_fuel
            else:
                log.efficiency = 0.0
