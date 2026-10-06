from collections import defaultdict

from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _prepare_hand_over_at_sale(self) -> None:
        super()._prepare_hand_over_at_sale()
        trip = self._get_hand_over_trip()
        if not trip:
            return
        location = self._get_hand_over_vehicle_location(trip)
        if not location:
            return
        self.action_unreserve()
        self.location_id = location
        self.move_ids.filtered(lambda move: move.state not in ("done", "cancel")).write(
            {
                "location_id": location.id,
                "trip_batch_id": trip.id,
                "trip_move_kind": "delivery",
            }
        )

    def _get_hand_over_trip(self):
        return self.env["stock.picking.batch"].search(
            [
                ("operator_id.user_id", "=", self.env.user.id),
                ("company_id", "in", self.company_id.ids),
                ("date_loaded", "!=", False),
                ("date_departure", "!=", False),
                ("date_return", "=", False),
            ],
            order="date_departure desc",
            limit=1,
        )

    def _get_hand_over_vehicle_location(self, trip):
        demand = defaultdict(float)
        for move in self.move_ids.filtered(
            lambda move: move.state not in ("done", "cancel")
        ):
            demand[move.product_id] += move.product_qty
        quants = self.env["stock.quant"].search(
            [
                ("location_id", "in", trip.trip_location_ids.ids),
                ("product_id", "in", [product.id for product in demand]),
                ("quantity", ">", 0),
            ]
        )
        for location in trip.trip_location_ids:
            free = defaultdict(float)
            for quant in quants.filtered(
                lambda quant, location=location: quant.location_id == location
            ):
                free[quant.product_id] += quant.quantity - quant.reserved_quantity
            if all(
                product.uom_id.compare(free[product], quantity) >= 0
                for product, quantity in demand.items()
            ):
                return location
        return self.env["stock.location"]
