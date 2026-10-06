from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    module_social_demo = fields.Boolean(
        string="Enable Demo Mode",
        groups="base.group_system",
    )
