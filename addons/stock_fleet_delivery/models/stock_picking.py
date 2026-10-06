from odoo import models
from odoo.exceptions import UserError

TRIP_MODES = (False, "own_fleet", "salesperson")


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_dispatch_mode(self):
        """How the goods leave: the carrier's mode, else the source location's.

        :rtype: str or bool
        """
        self.check_singleton()
        return self.carrier_id.dispatch_mode or self.location_id.dispatch_mode

    def _rides_trip_vehicle(self) -> bool:
        # Goods that leave with a third-party carrier or the customer do not ride
        # our vehicle; no carrier and no location mode still means our own.
        return super()._rides_trip_vehicle() and self._get_dispatch_mode() in TRIP_MODES

    def _trip_vehicle_returns(self) -> bool:
        # A salesperson delivers with their own car and carries on: their trip
        # ends at the last delivery, not back at the warehouse.
        return (
            super()._trip_vehicle_returns()
            and self._get_dispatch_mode() != "salesperson"
        )

    def _check_dispatch_requirements(self) -> None:
        super()._check_dispatch_requirements()
        for picking in self:
            picking_type = picking.picking_type_id
            if not (
                picking_type.code == "outgoing" and picking_type.dispatch_batch_required
            ):
                continue
            if (
                picking._get_dispatch_mode() == "third_party"
                and not picking.carrier_tracking_ref
            ):
                raise UserError(
                    self.env._(
                        "Transfer %(name)s leaves with a third-party carrier: "
                        "capture its tracking reference before validating it.",
                        name=picking.name,
                    )
                )
