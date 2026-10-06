from odoo import fields, models


class DeviceDevice(models.Model):
    _inherit = "device.device"

    employee_id = fields.Many2one(
        comodel_name="hr.employee",
        index=True,
        ondelete="set null",
        tracking=True,
        help="Employee assigned to this device",
    )
