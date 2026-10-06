from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    lazada_order_item_ids = fields.One2many(
        comodel_name="lazada.order.item",
        inverse_name="sale_order_line_id",
        string="Lazada Order Items",
    )
