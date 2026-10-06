from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    def _action_done(self, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        if self.env["res.groups"]._is_feature_enabled(
            "sale_stock_renting.group_rental_stock_picking"
        ):
            for sale_line in self.sale_line_id:
                if not sale_line._is_rental_kit():
                    continue
                incoming_done_moves = sale_line.move_ids.filtered(
                    lambda m: (
                        m.location_id == m.company_id.rental_loc_id
                        and m.state == "done"
                    )
                )
                if incoming_done_moves:
                    amount_kits_returned = sale_line._get_rental_kits_moved(
                        incoming_done_moves
                    )
                    current_qty_returned = amount_kits_returned - sale_line.qty_returned
                    _debug.logic(
                        "rental_kit_returned",
                        sale_line=sale_line.id,
                        kits=amount_kits_returned,
                        delta=current_qty_returned,
                        late=sale_line.order_id.is_late,
                    )
                    if current_qty_returned and sale_line.order_id.is_late:
                        sale_line._create_delay_line(current_qty_returned)
                    sale_line.qty_returned = amount_kits_returned
        return res

    def _set_rental_sm_qty(self):
        self.check_singleton()
        _debug.logic(
            "rental_move_qty",
            move=self.id,
            by="kit" if self.product_id.is_kit else "plain",
        )
        if self.product_id.is_kit:
            return self.with_context(skip_picking_assignation=True).action_explode()
        else:
            return super()._set_rental_sm_qty()
