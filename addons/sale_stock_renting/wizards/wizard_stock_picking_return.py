from odoo import models


class WizardStockPickingReturn(models.TransientModel):
    _inherit = "wizard.stock.picking.return"

    def _compute_product_return_moves(self) -> None:
        super()._compute_product_return_moves()
        for wizard in self:
            if wizard.product_return_moves:
                wizard.product_return_moves = wizard.product_return_moves.filtered(
                    lambda r: not r.move_id.sale_line_id.is_rental
                )
