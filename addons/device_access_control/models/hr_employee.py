import logging

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    def write(self, vals):
        res = super().write(vals)
        if "name" in vals:
            device_users = (
                self.env["access.device.user"]
                .sudo()
                .search(
                    [
                        ("employee_id", "in", self.ids),
                        ("state", "=", "synced"),
                        ("device_id.connection_state", "=", "connected"),
                    ]
                )
            )
            for du in device_users:
                try:
                    du.action_sync_to_device()
                except UserError:
                    _logger.warning(
                        "Re-sync after name change failed for %s",
                        du.display_name,
                    )
        return res
