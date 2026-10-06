from odoo import fields, models
from odoo.exceptions import UserError


class DeviceDevice(models.Model):
    _inherit = "device.device"

    enrollment_ids = fields.One2many(
        comodel_name="device.enrollment",
        inverse_name="device_id",
    )

    def write(self, vals):
        if "company_id" in vals:
            moved = self.filtered(
                lambda record: record.company_id.id != vals["company_id"]
            )
            if moved and self.env["device.enrollment"].with_privilege(
                "device_transport.privilege_validate_enrollment",
                reason="retain the company of enrolled operational identities",
            ).search_count([("device_id", "in", moved.ids)], limit=1):
                raise UserError(
                    self.env._(
                        "An enrolled operational device retains its company. Create a new operational identity for the receiving company."
                    )
                )
        return super().write(vals)
