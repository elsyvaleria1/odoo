from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_compare

_debug = DebugLog(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_fields_stock_barcode(self):
        return [
            "product_id",
            "location_id",
            "product_uom_qty",
            "product_uom_id",
            "move_line_ids",
            "packaging_uom_id",
            "quantity_packaging_uom",
        ]

    def split_uncompleted_moves(self):
        _debug.pipeline("barcode_split_uncompleted", moves=self)
        moves_to_reset = self.filtered(lambda m: m.picked and m.quantity == 0)
        moves_to_backorder = (self - moves_to_reset).filtered(
            lambda move: move.picked and move.state not in ["done", "cancel"]
        )
        for move in moves_to_reset:
            move.move_line_ids.unlink()
            move.quantity = move.product_uom_qty
            move.picked = False
        new_moves = moves_to_backorder._create_backorder()
        new_moves.with_context(bypass_entire_pack=True).filtered(
            lambda m: (
                m.procure_method == "make_to_order"
                or not m._is_assign_at_confirm_required()
            )
        )._action_assign()
        if new_moves:
            moves_to_clean = self - new_moves
            for move in moves_to_clean:
                for move_line in move.move_line_ids:
                    if move_line.quantity == 0 and move_line.picked:
                        move_line.unlink()
            group_new_moves = new_moves.grouped("picking_id")
            group_moves_to_backorder = moves_to_backorder.grouped("picking_id")
            for picking, moves_to_merge in group_new_moves.items():
                moves_to_merge._merge_moves(
                    merge_into=group_moves_to_backorder[picking]
                )
        return new_moves

    def _truncate_overreserved_moves(self, barcode_quantities) -> None:
        _debug.logic("barcode_truncate_overreserved", moves=self)
        for move in self:
            if not move.picked or move.state in ("done", "cancel"):
                continue
            move_qties = barcode_quantities.get(str(move.id), False)
            if move_qties:
                max_reserved_qty = max(
                    move_qties["quantity_done"], move_qties["reserved_uom_qty"]
                )
                if (
                    float_compare(
                        move.quantity,
                        max_reserved_qty,
                        precision_rounding=move.product_id.uom_id.rounding,
                    )
                    > 0
                ):
                    move.with_context(
                        {"unreserve_unpicked_only": True}
                    ).quantity = max_reserved_qty

    def post_barcode_process(self, barcode_quantities):
        _debug.pipeline("barcode_post_process", moves=self)
        new_moves = self.split_uncompleted_moves()
        self._truncate_overreserved_moves(barcode_quantities)
        return new_moves
