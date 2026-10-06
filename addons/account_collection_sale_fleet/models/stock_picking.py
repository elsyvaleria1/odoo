from odoo import models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _rides_trip_vehicle(self) -> bool:
        return super()._rides_trip_vehicle() and not self.is_handed_over_at_sale

    def _requires_delivery_proof(self):
        return super()._requires_delivery_proof() and not self.is_handed_over_at_sale

    def _is_auto_batchable(self, picking=None) -> bool:
        return super()._is_auto_batchable(picking) and not self.is_handed_over_at_sale

    def _prepare_hand_over_at_sale(self) -> None:
        super()._prepare_hand_over_at_sale()
        departed = self.filtered("batch_id.date_departure")
        if departed:
            raise UserError(
                self.env._(
                    "%(pickings)s already left on trip %(trips)s: deliver them from "
                    "that trip instead of handing them over here.",
                    pickings=", ".join(departed.mapped("name")),
                    trips=", ".join(departed.batch_id.mapped("name")),
                )
            )
        self.filtered("batch_id").batch_id = False
