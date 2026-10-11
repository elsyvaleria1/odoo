from odoo import api, models
from odoo.exceptions import UserError

DRIVER_TRIP_STATES = ("planned", "loaded", "in_transit")


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    @api.model
    def _trip_driver_trips(self) -> list:
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
        for batch in self.filtered("trip_offline_event_ids"):
            batch._trip_apply_offline_events()
        return res

    def _trip_after_unload(self):
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
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": f"/stock_fleet_trace/driver?trip={self.id}",
            "target": "new",
        }
