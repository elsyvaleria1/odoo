from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    pos_module_pos_urban_piper = fields.Boolean(
        related="pos_config_id.module_pos_urban_piper",
        string="Urban Piper",
        readonly=False,
        help="Manage your online orders with Urban Piper.",
    )
    module_pos_tyro = fields.Boolean(
        string="Tyro Payment Terminal",
        help="The transactions are processed by Tyro. Set your Tyro credentials on the related payment method.",
    )
