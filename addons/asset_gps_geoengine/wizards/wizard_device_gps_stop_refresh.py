from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import UserError


class WizardDeviceGpsStopRefresh(models.TransientModel):
    _name = "wizard.device.gps.stop.refresh"
    _description = "Refresh Vehicle Stops from GPS Positions"

    date_from = fields.Date(
        default=lambda self: fields.Date.context_today(self) - timedelta(days=7),
        required=True,
    )
    date_to = fields.Date(
        default=fields.Date.context_today,
        required=True,
        help="Inclusive.",
    )
    device_ids = fields.Many2many(
        comodel_name="device.device",
        string="Vehicles",
        domain=[("is_gps_device", "=", True)],
        help="Empty means every GPS device.",
    )

    def action_refresh(self):
        self.check_singleton()
        if self.date_from > self.date_to:
            raise UserError(
                self.env._("The start date must not be after the end date.")
            )
        self.env["device.gps.stop"]._refresh(
            self.date_from, self.date_to, devices=self.device_ids or None
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Stops refreshed."),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
