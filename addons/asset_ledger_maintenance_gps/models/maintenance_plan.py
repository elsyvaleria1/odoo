from odoo import api, models


class MaintenancePlan(models.Model):
    _inherit = "maintenance.plan"

    @api.depends("asset_id", "asset_id.odometer", "asset_id.gps_device_id")
    def _compute_current_odometer(self) -> None:
        super()._compute_current_odometer()
        for plan in self.filtered(
            lambda p: p.asset_id.trace_id and not p.current_odometer
        ):
            plan.current_odometer = (
                plan.asset_id.trace_id._get_current_gps_odometer() or 0.0
            )
