from odoo import fields, models


class StockConfig(models.Model):
    _inherit = "stock.config"

    stock_confirmation_wa_template_id = fields.Many2one(
        comodel_name="whatsapp.template",
        string="WhatsApp Template",
        help="Send WhatsApp to the customer once the order is delivered.",
    )
