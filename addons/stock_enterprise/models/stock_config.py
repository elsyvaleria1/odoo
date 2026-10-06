from odoo import fields, models


class StockConfig(models.Model):
    _inherit = "stock.config"

    stock_confirmation_type = fields.Selection(
        selection_add=[("whatsapp", "Whatsapp")],
        ondelete={"whatsapp": "set default"},
    )
