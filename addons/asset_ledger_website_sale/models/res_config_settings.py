from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    whatsapp_sales_number = fields.Char(
        related="website_id.whatsapp_sales_number",
        readonly=False,
    )
