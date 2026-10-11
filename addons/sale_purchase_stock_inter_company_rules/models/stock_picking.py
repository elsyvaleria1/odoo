from odoo import Command, api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self, **validate_kwargs):
        res = super().button_validate(**validate_kwargs)
        for picking in self:
            if not picking.sale_id or picking.picking_type_code not in (
                "outgoing",
                "dropship",
            ):
                _debug.logic(
                    "intercompany_sync_skipped",
                    picking=picking,
                    reason="no_sale_order" if not picking.sale_id else "picking_type",
                    code=picking.picking_type_code,
                )
                continue
            company_rec = self.env["res.company"]._find_company_from_partner(
                picking.sale_id.partner_id.id
            )
            _debug.logic(
                "intercompany_company_resolved",
                picking=picking,
                company=company_rec or None,
                sync=bool(company_rec)
                and company_rec.intercompany_sync_delivery_receipt,
            )
            if company_rec and company_rec.intercompany_sync_delivery_receipt:
                sale_order = picking.sale_id
                purchase_order = (
                    self.env["purchase.order"]
                    .sudo()
                    .search(
                        [
                            ("name", "=", sale_order.client_order_ref),
                            ("company_id", "=", company_rec.id),
                        ]
                    )
                )
                receipts = purchase_order.picking_ids.filtered(
                    lambda p: p.picking_type_code in ("incoming", "dropship")
                )
                _debug.pipeline(
                    "intercompany_receipts_found",
                    picking=picking,
                    order=sale_order,
                    purchase=purchase_order,
                    receipts=receipts,
                )
                if not receipts:
                    continue
                for move in picking.move_ids:
                    if move.state != "done" or move.product_id.company_id:
                        _debug.logic(
                            "intercompany_move_skipped",
                            move=move,
                            state=move.state,
                            company_owned=bool(move.product_id.company_id),
                        )
                        continue
                    receipt_move = self._find_corresponding_move(move, receipts)
                    _debug.logic(
                        "intercompany_move_matched",
                        move=move,
                        receipt_move=receipt_move or None,
                        matched=bool(receipt_move),
                    )
                    if receipt_move:
                        receipt_move.write(
                            {
                                "move_line_ids": [
                                    *[
                                        Command.delete(ml.id)
                                        for ml in receipt_move.move_line_ids
                                    ],
                                    *[
                                        Command.create(ml_vals)
                                        for ml_vals in self._prepare_move_lines(
                                            move, receipt_move
                                        )
                                    ],
                                ]
                            }
                        )
                        _debug.lifecycle(
                            "intercompany_move_lines_mirrored",
                            move=move,
                            receipt_move=receipt_move,
                            lines=len(move.move_line_ids),
                        )
                        receipt_move.move_line_ids._apply_putaway_strategy()
        return res

    @api.model
    def _find_corresponding_move(self, move_orig, candidate_pickings):
        candidates = candidate_pickings.move_ids.filtered(
            lambda move: move.product_id == move_orig.product_id and not move.picked
        )
        if not candidates:
            _debug.logic(
                "corresponding_move_unresolved",
                move=move_orig,
                product=move_orig.product_id,
                reason="no_unpicked_candidate",
            )
            return False
        exact_qty_match = candidates.filtered(
            lambda move: move.product_uom_qty == move_orig.product_uom_qty
        )
        _debug.logic(
            "corresponding_move_resolved",
            move=move_orig,
            candidates=len(candidates),
            by="exact_qty" if exact_qty_match else "first_candidate",
        )
        return (exact_qty_match or candidates)[:1]

    @api.model
    def _prepare_move_lines(self, delivery_move, receipt_move):
        move_lines_vals = []
        for move_line in delivery_move.move_line_ids:
            ml_vals = receipt_move._prepare_move_line_vals(quantity=0)
            if move_line.trace_id:
                ml_vals["lot_name"] = move_line.trace_id.name
                if not move_line.trace_id.company_id:
                    ml_vals["trace_id"] = move_line.trace_id.id
            ml_vals["quantity"] = move_line.quantity
            ml_vals["picked"] = True
            move_lines_vals.append(ml_vals)
        return move_lines_vals
