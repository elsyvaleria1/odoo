from odoo import models


class StockWarehouseOrderpoint(models.Model):
    _inherit = "stock.warehouse.orderpoint"

    def _prepare_action_orderpoint_replenish(self):
        return super(
            StockWarehouseOrderpoint, self.with_context(ignore_rental_returns=True)
        )._prepare_action_orderpoint_replenish()

    def _prepare_product_context(self):
        context = super()._prepare_product_context()
        context["ignore_rental_returns"] = True
        return context

    def _get_quantity_in_progress(self):
        res = super()._get_quantity_in_progress()
        rental_loc_ids = self.env.companies.rental_loc_id.ids
        for orderpoint in self:
            if not orderpoint.product_id.rent_ok:
                continue
            domain = [
                ("product_id", "=", orderpoint.product_id.id),
                (
                    "state",
                    "in",
                    ["confirmed", "assigned", "waiting", "partially_available"],
                ),
                ("date", "<=", orderpoint.lead_horizon_date),
                "|",
                ("location_id", "in", rental_loc_ids),
                "|",
                ("location_dest_id", "in", rental_loc_ids),
                ("location_final_id", "in", rental_loc_ids),
                "|",
                ("location_id.warehouse_id", "=", orderpoint.warehouse_id.id),
                ("location_dest_id.warehouse_id", "=", orderpoint.warehouse_id.id),
            ]
            rental_moves = self.env["stock.move"].search(domain, order="date, id")
            outs_qty, current_qty, max_missing_qty = 0, 0, 0
            for move in rental_moves:
                if move.location_id.id in rental_loc_ids:
                    current_qty += move.product_qty
                else:
                    outs_qty += move.product_qty
                    current_qty -= move.product_qty
                    max_missing_qty = min(max_missing_qty, current_qty)
            res[orderpoint.id] += outs_qty + max_missing_qty
        return res
