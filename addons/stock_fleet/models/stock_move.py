from odoo import models


class StockMove(models.Model):
    _inherit = "stock.move"

    def _trip_goods_weight(self):
        """What the demand of these moves weighs, without pallets or packaging.

        :rtype: float
        """
        return sum(move.product_id._trip_weight(move.product_qty) for move in self)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _trip_goods_weight(self):
        """What the goods of these lines weigh, without pallets or packaging.

        :rtype: float
        """
        return sum(
            line.product_id._trip_weight(line.quantity_product_uom) for line in self
        )
