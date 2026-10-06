from collections import defaultdict

from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_is_zero

_debug = DebugLog(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _update_reserved_quantity(
        self,
        need,
        location_id,
        trace_id=None,
        package_id=None,
        owner_id=None,
        strict=True,
    ):
        _debug.logic("fsm_reserved_qty_update", moves=self)
        if self.product_id.tracking == "none":
            return super()._update_reserved_quantity(
                need,
                location_id,
                trace_id=trace_id,
                package_id=package_id,
                owner_id=owner_id,
                strict=strict,
            )
        lot = trace_id
        if (
            self.sale_line_id.sudo().fsm_trace_id
            and self.location_dest_id == self.location_final_id
        ):
            lot = self.sale_line_id.sudo().fsm_trace_id or lot
        if lot and self.product_id.tracking != "serial":
            return super()._update_reserved_quantity(
                need,
                location_id,
                trace_id=lot,
                package_id=package_id,
                owner_id=owner_id,
                strict=strict,
            )

        so_lines_with_fsm_lot = self.sale_line_id.sudo().filtered(
            lambda l: l.product_id == self.product_id and l.fsm_trace_id
        )
        if not so_lines_with_fsm_lot:
            return super()._update_reserved_quantity(
                need,
                location_id,
                trace_id=trace_id,
                package_id=package_id,
                owner_id=owner_id,
                strict=strict,
            )

        already_used_by_lots = defaultdict(float)
        sibling_moves = (
            self.move_dest_ids.move_orig_ids
            if self.move_dest_ids
            else self.picking_id.move_ids
        )
        for ml in sibling_moves.move_line_ids:
            qty = ml.quantity
            qty = ml.product_uom_id._get_quantity_in_unit(qty, ml.product_id.uom_id)
            already_used_by_lots[ml.trace_id] += qty

        reserved = 0
        for so_line in so_lines_with_fsm_lot:
            if float_is_zero(need, precision_rounding=self.product_id.uom_id.rounding):
                return reserved
            lot = so_line.fsm_trace_id
            sol_qty = so_line.product_uom_id._get_quantity_in_unit(
                so_line.product_qty, so_line.product_id.uom_id
            )
            lot_need = max(0, sol_qty - already_used_by_lots[lot])
            lot_need = min(need, lot_need)
            taken = super()._update_reserved_quantity(
                lot_need,
                location_id,
                trace_id=lot,
                package_id=package_id,
                owner_id=owner_id,
                strict=strict,
            )
            need -= taken
            reserved += taken

        if float_is_zero(need, precision_rounding=self.product_id.uom_id.rounding):
            return reserved

        reserved += super()._update_reserved_quantity(
            need,
            location_id,
            trace_id=trace_id,
            package_id=package_id,
            owner_id=owner_id,
            strict=strict,
        )
        return reserved
