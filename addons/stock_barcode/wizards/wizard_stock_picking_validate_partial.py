from odoo import api, fields, models


class WizardStockPickingValidatePartial(models.TransientModel):
    _inherit = "wizard.stock.picking.validate.partial"

    empty_move_count = fields.Integer(compute="_compute_not_fully_processed_move_count")
    partial_move_count = fields.Integer(
        compute="_compute_not_fully_processed_move_count"
    )

    @api.depends("pick_ids")
    def _compute_not_fully_processed_move_count(self) -> None:
        for backorder in self:
            moves = backorder.pick_ids.move_ids
            backorder.empty_move_count = len(
                moves.filtered(lambda mv: mv.product_uom_qty and not mv.picked)
            )
            backorder.partial_move_count = len(
                moves.filtered(
                    lambda mv: mv.product_uom_qty > mv.quantity and mv.picked
                )
            )
