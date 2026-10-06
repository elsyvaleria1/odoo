from odoo import api, models
from odoo.exceptions import UserError

# Trips a driver still works from the phone.
DRIVER_TRIP_STATES = ("planned", "loaded", "in_transit")


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    @api.model
    def _trip_driver_trips(self) -> list:
        """The traced trips the current user drives or supervises, still to work.

        :return: id, name, vehicle, trip state and stop count of each trip
        :rtype: list
        """
        user = self.env.user
        trips = self.search(
            [
                ("picking_type_id.trip_trace", "=", True),
                ("trip_state", "in", DRIVER_TRIP_STATES),
                "|",
                ("operator_id.user_id", "=", user.id),
                ("supervisor_id", "=", user.id),
            ],
            order="id",
        )
        return [
            {
                "id": trip.id,
                "name": trip.name,
                "vehicle": trip.vehicle_id.display_name or False,
                "state": trip.trip_state,
                "stop_count": len(trip.picking_ids),
            }
            for trip in trips
        ]

    def action_depart(self):
        res = super().action_depart()
        # Stop results the phone captured before the departure was stamped.
        for batch in self.filtered("trip_offline_event_ids"):
            batch._trip_apply_offline_events()
        return res

    def _trip_after_unload(self):
        # Stop results captured on a trip that never left close nothing: they
        # are set aside, with their reason, and the supervisor is told.
        if not self.date_departure:
            deferred = self.trip_offline_event_ids.filtered(
                lambda e: e.state == "pending"
            )
            for event in deferred:
                event._write_state(
                    {
                        "state": "dismissed",
                        "error": self.env._(
                            "The trip was unloaded without departing: nothing was "
                            "delivered on the road."
                        ),
                    }
                )
            if deferred:
                self.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=(self.supervisor_id or self.env.user).id,
                    summary=self.env._(
                        "Trip %s was unloaded with stop results from the phone",
                        self.name,
                    ),
                    note=self.env._(
                        "%(count)s results captured on the phone before the trip "
                        "departed were set aside: check them in the trip's offline "
                        "events.",
                        count=len(deferred),
                    ),
                )
        return super()._trip_after_unload()

    def action_trip_release_phone_head(self) -> None:
        """The phone that reported unsent events is lost: let the trip return."""
        self.check_singleton()
        if not (
            self.env.user == self.supervisor_id
            or self.env["stock.trip.offline.event"].has_access("unlink")
        ):
            raise UserError(
                self.env._(
                    "The phone of trip %s is released by its supervisor or a stock "
                    "manager.",
                    self.name,
                )
            )
        head = self.trip_offline_phone_head
        self.trip_offline_phone_head = False
        self.message_post(
            body=self.env._(
                "Phone released: the events it held beyond %(head)s will not arrive.",
                head=head or "-",
            )
        )

    def action_trip_open_driver_screen(self) -> dict:
        """Open the phone's driver screen on this trip."""
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": f"/stock_fleet_trace/driver?trip={self.id}",
            "target": "new",
        }
