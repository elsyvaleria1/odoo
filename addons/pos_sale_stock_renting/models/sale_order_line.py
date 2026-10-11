from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _compute_qty_transferred(self):
        super()._compute_qty_transferred()

        if not self.with_context(
            skip_pos_rental_pickings_check=True
        )._are_rental_pickings_enabled():
            return

        for line in self:
            if line.is_rental and line.product_id.type == "consu":
                qty = 0.0
                outgoing_moves, _ = line.with_context(
                    skip_pos_rental_pickings_check=True
                )._get_stock_moves_outgoing_incoming()
                for move in outgoing_moves:
                    if move.state != "done":
                        continue
                    qty += move.product_uom_id._get_quantity_in_unit(
                        move.quantity, line.product_uom_id, rounding_method="HALF-UP"
                    )
                line.qty_transferred = qty
                if all(
                    picking.state == "done"
                    for picking in line.pos_order_line_ids.order_id.picking_ids
                ):
                    line.qty_transferred += sum(
                        (
                            self._convert_qty(line, pos_line.qty, "p2s")
                            for pos_line in line.pos_order_line_ids
                            if line.product_id.type != "service"
                        ),
                        0,
                    )

    def _prepare_qty_transferred(self):
        delivered_qties = super()._prepare_qty_transferred()

        if not self.with_context(
            skip_pos_rental_pickings_check=True
        )._are_rental_pickings_enabled():
            return delivered_qties

        for line in self:
            if line.is_rental and line.product_id.type == "consu":
                qty = 0.0
                outgoing_moves, _ = line.with_context(
                    skip_pos_rental_pickings_check=True
                )._get_stock_moves_outgoing_incoming()
                for move in outgoing_moves:
                    if move.state != "done":
                        continue
                    qty += move.product_uom_id._get_quantity_in_unit(
                        move.quantity, line.product_uom_id, rounding_method="HALF-UP"
                    )
                delivered_qties[line] = qty
                if (
                    all(
                        picking.state == "done"
                        for picking in line.pos_order_line_ids.order_id.picking_ids
                    )
                    and line.product_id.type != "service"
                ):
                    delivered_qties[line] += sum(
                        (
                            self._convert_qty(line, pos_line.qty, "p2s")
                            for pos_line in line.pos_order_line_ids
                        ),
                        0,
                    )
        return delivered_qties

    def _are_rental_pickings_enabled(self):
        if super()._are_rental_pickings_enabled():
            return True
        if not self.env.context.get("skip_pos_rental_pickings_check"):
            return False
        return any(line.sudo().pos_order_line_ids for line in self)
