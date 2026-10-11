from odoo import fields, models


class StockMove(models.Model):
    _inherit = "stock.move"

    lazada_order_item_ids = fields.One2many(
        comodel_name="lazada.order.item",
        inverse_name="stock_move_id",
        string="Lazada Order Items",
    )

    def initialize_lazada_order_items(self) -> None:
        for move in self:
            move.lazada_order_item_ids = move.sale_line_id.lazada_order_item_ids
