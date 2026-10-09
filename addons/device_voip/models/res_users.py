from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    phone_device_ids = fields.One2many(
        comodel_name="device.device",
        inverse_name="user_id",
        string="Phones",
    )
