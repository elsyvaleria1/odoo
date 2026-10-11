from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _trip_goods_weight(self):
        return sum(move.product_id._trip_weight(move.product_qty) for move in self)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _trip_goods_weight(self):
        return sum(
            line.product_id._trip_weight(line.quantity_product_uom) for line in self
        )
