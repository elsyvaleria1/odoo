from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    asset_id = fields.Many2one(domain="[('kind_id.code', '=', 'machinery')]")
    theoretical_fuel_efficiency = fields.Float(
        related="asset_id.product_id.fuel_efficiency_theoretical",
        help="Fuel efficiency the machinery's model is rated for.",
    )
    actual_fuel_efficiency = fields.Float(
        compute="_compute_asset_fuel_efficiency",
        help="Average fuel efficiency from the last 10 fuel logs",
    )
    fuel_efficiency_deviation = fields.Float(
        compute="_compute_asset_fuel_efficiency",
        help="Percentage deviation from theoretical performance",
    )

    @api.depends("asset_id", "theoretical_fuel_efficiency")
    def _compute_asset_fuel_efficiency(self) -> None:
        asset_log_model = self.env["resource.asset.log"]
        for wc in self:
            if not wc.asset_id:
                wc.actual_fuel_efficiency = 0.0
                wc.fuel_efficiency_deviation = 0.0
                continue
            recent_logs = asset_log_model.search(
                [
                    ("asset_id", "=", wc.asset_id.id),
                    ("log_type", "=", "fuel"),
                ],
                order="date desc",
                limit=20,
            )
            logs = recent_logs.filtered(lambda line: line.efficiency > 0)[:10]
            _debug.logic(
                "fuel_efficiency_sample",
                workcenter=wc.id,
                asset=wc.asset_id.id,
                fetched=len(recent_logs),
                usable=len(logs),
                theoretical=wc.theoretical_fuel_efficiency,
            )
            if logs:
                wc.actual_fuel_efficiency = sum(logs.mapped("efficiency")) / len(logs)
                if wc.theoretical_fuel_efficiency:
                    deviation = (
                        (wc.actual_fuel_efficiency - wc.theoretical_fuel_efficiency)
                        / wc.theoretical_fuel_efficiency
                        * 100
                    )
                    wc.fuel_efficiency_deviation = deviation
                else:
                    wc.fuel_efficiency_deviation = 0.0
            else:
                wc.actual_fuel_efficiency = 0.0
                wc.fuel_efficiency_deviation = 0.0
