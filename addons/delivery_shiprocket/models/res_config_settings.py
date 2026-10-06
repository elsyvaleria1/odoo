from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_delivery_shiprocket = fields.Boolean(string="Shiprocket Connector")
