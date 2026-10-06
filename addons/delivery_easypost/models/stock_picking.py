from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    ep_order_ref = fields.Char(
        string="Easypost Order Reference",
        copy=False,
    )
