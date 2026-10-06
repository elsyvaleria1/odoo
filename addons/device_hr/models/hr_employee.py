from typing import Any

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    device_ids = fields.One2many(
        comodel_name="device.device",
        inverse_name="employee_id",
        groups="device.group_device_user",
        help="Remote devices assigned to this employee, of any kind.",
    )
    device_count = fields.Count(
        count_of="device_ids",
        groups="device.group_device_user",
    )

    def action_view_devices(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "name": self.env._("Devices: %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "device.device",
            "view_mode": "list,form",
            "domain": [("employee_id", "=", self.id)],
            "context": {
                "default_employee_id": self.id,
            },
        }

    def action_view_tracking_history(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "name": self.env._("Tracking History: %s") % self.name,
            "type": "ir.actions.act_window",
            "res_model": "device.data.log.gps",
            "view_mode": "list,form",
            "domain": [("device_id.employee_id", "=", self.id)],
            "context": {
                "search_default_last_week": 1,
            },
        }
