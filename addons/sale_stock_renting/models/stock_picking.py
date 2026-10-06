from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _is_backorder_ignore_required(self) -> bool:
        return super()._is_backorder_ignore_required() and not any(
            move.sale_line_id.is_rental for move in self.move_ids
        )
