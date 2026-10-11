from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_procurement_qty(self, previous_product_qty=False):
        qty = super()._get_procurement_qty(previous_product_qty)
        if (
            self.is_rental
            and self.env["res.groups"]._is_feature_enabled(
                "sale_stock_renting.group_rental_stock_picking"
            )
            and "phantom" in self.product_id.bom_ids.mapped("type")
        ):
            bom = self.env["mrp.bom"]._get_bom_by_product(
                self.product_id, bom_type="phantom"
            )[self.product_id]
            outgoing_moves = self.move_ids.filtered(
                lambda m: (
                    m.location_dest_id == m.company_id.rental_loc_id
                    and m.state != "cancel"
                    and m.location_dest_usage != "inventory"
                    and m.product_id in bom.bom_line_ids.product_id
                )
            )
            filters = {
                "incoming_moves": lambda m: (
                    m.location_dest_id == m.company_id.rental_loc_id
                    and (
                        not m.origin_returned_move_id
                        or (m.origin_returned_move_id and m.to_refund)
                    )
                ),
                "outgoing_moves": lambda m: (
                    m.location_dest_id != m.company_id.rental_loc_id and m.to_refund
                ),
            }
            order_qty = (
                previous_product_qty.get(self.id, 0)
                if previous_product_qty
                else self.product_qty
            )
            order_qty = self.product_uom_id._get_quantity_in_unit(
                order_qty, bom.product_uom_id
            )
            qty_to_compute = outgoing_moves._get_kit_quantity(
                self.product_id, order_qty, bom, filters
            )
            qty = bom.product_uom_id._get_quantity_in_unit(
                qty_to_compute, self.product_uom_id
            )
        return qty

    def _is_rental_kit(self) -> bool:
        return bool(
            self.is_rental and "phantom" in self.product_id.bom_ids.mapped("type")
        )

    def _get_rental_kits_moved(self, moves):
        self.check_singleton()
        bom = self.env["mrp.bom"]._get_bom_by_product(
            self.product_id, bom_type="phantom"
        )[self.product_id]
        kits = moves._get_kit_quantity(
            self.product_id,
            self.product_uom_id._get_quantity_reconcile(
                self.product_uom_qty, bom.product_uom_id
            ),
            bom,
            {
                "incoming_moves": lambda m: m.location_id == m.company_id.rental_loc_id,
                "outgoing_moves": lambda m: (
                    m.location_dest_id == m.company_id.rental_loc_id
                ),
            },
        )
        return bom.product_uom_id._get_quantity_reconcile(kits, self.product_uom_id)

    def _get_rental_kits_delivered(self):
        self.check_singleton()
        delivered_moves = self.move_ids.filtered(
            lambda m: (
                m.state == "done" and m.location_dest_id == m.company_id.rental_loc_id
            )
        )
        if not delivered_moves:
            return 0.0
        return -self._get_rental_kits_moved(delivered_moves)

    def _compute_qty_transferred(self):
        if not self._are_rental_pickings_enabled():
            return super()._compute_qty_transferred()
        self.fetch(["is_rental", "product_id"])
        kits = self.filtered(lambda line: line._is_rental_kit())
        for line in kits:
            line.qty_transferred = line._get_rental_kits_delivered()
        return super(SaleOrderLine, self - kits)._compute_qty_transferred()

    def _prepare_qty_transferred(self):
        if not self._are_rental_pickings_enabled():
            return super()._prepare_qty_transferred()
        self.fetch(["is_rental", "product_id"])
        kits = self.filtered(lambda line: line._is_rental_kit())
        delivered_qties = super(SaleOrderLine, self - kits)._prepare_qty_transferred()
        delivered_qties.update(
            {line: line._get_rental_kits_delivered() for line in kits}
        )
        return delivered_qties
