from odoo import fields, models


class DeviceDevice(models.Model):
    _inherit = "device.device"

    asset_operator_id = fields.Many2one(
        related="asset_id.operator_employee_id",
        store=True,
        help="Current operator/driver assigned to the linked asset",
    )
    asset_license_plate = fields.Char(
        related="asset_id.license_plate",
        help="License plate of the linked asset",
    )
