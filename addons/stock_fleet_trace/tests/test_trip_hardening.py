from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

from .common import TripFixtureMixin


@tagged("post_install", "-at_install")
class TestTripHardening(TripFixtureMixin, TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.not_ordered = cls.env.ref("stock_fleet_trace.unbatch_reason_not_ordered")

    def _event(self, uuid, event_type, picking=None, **payload):
        return {
            "client_uuid": uuid,
            "event_type": event_type,
            "picking_id": picking.id if picking else False,
            "payload": payload,
            "captured_at": "2026-09-29T09:30:00-06:00",
            "latitude": 20.6597,
            "longitude": -103.3496,
            "device_uuid": "phone-1",
        }

    def _chain(self, trip, events, head=None):
        Event = self.env["stock.trip.offline.event"]
        chain_hash = trip._trip_last_event_hash() if head is None else head
        for event in events:
            event["prev_hash"] = chain_hash
            event["event_hash"] = chain_hash = Event._trip_hash_event(event)
        return events

    def _send(self, trip, events, head=None):
        return trip.with_user(self.driver_user)._trip_receive_offline_events(
            events, head=head
        )

    def _stop_result(self, picking, delivered, reason=None):
        wizard = (
            self.env["wizard.stock.trip.stop.result"]
            .with_context(default_picking_id=picking.id)
            .create({})
        )
        for line in wizard.line_ids:
            line.qty_delivered = delivered
            if line.qty_rejected:
                line.reason_id = reason
        wizard.action_confirm()

    def _spill(self, trip, quantity, picking=None):
        incident = self.env["stock.trip.incident"].create(
            {
                "batch_id": trip.id,
                "incident_type": "spill",
                "description": "A sack broke",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": quantity,
                            "picking_id": picking.id if picking else False,
                        }
                    )
                ],
            }
        )
        incident.with_user(self.supervisor).action_approve()
        return incident

    def _handover(self, trip):
        action = (
            self.env["wizard.stock.trip.handover"]
            .with_user(self.supervisor)
            .create(
                {
                    "batch_id": trip.id,
                    "vehicle_id": self.rescue_vehicle.id,
                    "operator_id": self.rescue_driver.id,
                    "odometer_departure": 500.0,
                    "fuel_departure": 60.0,
                    "reason": "Engine failure",
                }
            )
            .action_confirm()
        )
        return self.env["stock.picking.batch"].browse(action["res_id"])

    def _rows(self, trip):
        return {row["picking"]: row for row in trip._trip_report_stops()}

    def test_after_a_gap_the_rest_of_the_same_sync_is_still_applied(self):
        first, second = self._delivery(5), self._delivery(2)
        trip = self._trip(first | second)
        trip.action_depart()
        events = self._chain(
            trip,
            [
                self._event("gap-1", "deliver", first),
                self._event("gap-2", "deliver", second),
            ],
            head="a-lost-event",
        )

        result = self._send(trip, events)

        self.assertEqual(result["gap-1"]["state"], "review")
        self.assertEqual(result["gap-2"]["state"], "applied", result)
        self.assertEqual(second.state, "done")
        self.assertTrue(trip.trip_offline_chain_broken)

    def test_a_delivery_captured_before_departure_waits_for_it(self):
        delivery = self._delivery(5)
        trip = self._trip(delivery)
        trip.action_trip_load()
        events = self._chain(trip, [self._event("early", "deliver", delivery)])

        result = self._send(trip, events)

        self.assertEqual(result["early"]["state"], "pending")
        trip.action_depart()
        self.assertEqual(trip.trip_offline_event_ids.state, "applied")
        self.assertEqual(delivery.state, "done")

    def test_an_event_for_an_unknown_delivery_does_not_fail_the_sync(self):
        delivery = self._delivery(5)
        trip = self._trip(delivery)
        trip.action_depart()
        ghost = self.env["stock.picking"].browse(999999999)
        events = self._chain(
            trip,
            [
                self._event("ghost", "deliver", ghost),
                self._event("real", "deliver", delivery),
            ],
        )

        result = self._send(trip, events)

        self.assertEqual(result["ghost"]["state"], "review")
        self.assertIn("does not exist", result["ghost"]["error"])
        self.assertEqual(result["real"]["state"], "applied", result)

    def test_a_scan_for_another_trips_delivery_goes_to_review(self):
        delivery, stranger = self._delivery(5), self._delivery(1)
        trip = self._trip(delivery)
        trip.action_depart()
        events = self._chain(
            trip, [self._event("stray-scan", "scan", stranger, code="L-001")]
        )

        result = self._send(trip, events)

        self.assertEqual(result["stray-scan"]["state"], "review")
        self.assertFalse(stranger.trip_scan_ids)

    def test_a_lost_phone_is_released_so_the_trip_can_return(self):
        delivery = self._delivery(5)
        trip = self._trip(delivery)
        trip.action_depart()
        delivery.action_deliver()
        self._send(trip, [], head="events-that-never-came")
        trip.write({"odometer_return": 1100.0, "fuel_return": 40.0})
        with self.assertRaisesRegex(UserError, "unsent events"):
            trip.action_return()

        trip.with_user(self.supervisor).action_trip_release_phone_head()
        trip.action_return()

        self.assertTrue(trip.date_return)
        with self.assertRaisesRegex(UserError, "supervisor or a stock manager"):
            trip.with_user(self.driver_user).action_trip_release_phone_head()

    def test_the_phone_gets_whole_delivery_reasons_and_reportable_incidents(self):
        trip = self._trip(self._delivery(1))

        package = trip.with_user(self.driver_user)._trip_offline_package()

        self.assertTrue(package["unbatch_reasons"])
        self.assertNotIn("line", {r["scope"] for r in package["unbatch_reasons"]})
        codes = {t["code"] for t in package["incident_types"]}
        self.assertNotIn("fuel", codes)
        self.assertNotIn("driver_change", codes)

    def test_a_rescue_trip_sheet_adds_up_after_a_spill(self):
        first, rest = self._delivery(5), self._delivery(2)
        trip = self._trip(first | rest)
        trip.action_trip_load()
        trip.action_depart()
        first.action_deliver()
        self._spill(trip, 1, rest)
        rescue = self._handover(trip)
        rest.action_deliver()

        rows = self._rows(trip)
        rescue_rows = self._rows(rescue)

        self.assertEqual(
            (rows[rest]["departure"], rows[rest]["written_off"]), (40.0, 20.0)
        )
        self.assertEqual(rows[rest]["handed_over"], 20.0)
        self.assertEqual(rows[rest]["back"], 0.0)
        self.assertEqual(rescue.weight_departure, 20.0)
        self.assertEqual(
            (rescue_rows[rest]["departure"], rescue_rows[rest]["delivered"]),
            (20.0, 20.0),
        )
        self.assertEqual(rescue_rows[rest]["back"], 0.0)
        self.assertTrue(trip._trip_report_weights_match(list(rows.values())))
        self.assertTrue(rescue._trip_report_weights_match(list(rescue_rows.values())))
        self.assertEqual(
            trip._trip_report_breakdown(rescue).trip_rescue_batch_id, rescue
        )

    def test_a_spill_of_rejected_goods_does_not_shorten_another_delivery(self):
        rejecting, other = self._delivery(5), self._delivery(4)
        trip = self._trip(rejecting | other)
        trip.action_trip_load()
        trip.action_depart()
        self._stop_result(rejecting, 3, reason=self.not_ordered)
        self._spill(trip, 2)

        other_reserved = sum(other.move_ids.move_line_ids.mapped("quantity"))
        rows = self._rows(trip)

        self.assertEqual(other_reserved, 4)
        self.assertEqual(rows[other]["written_off"], 0.0)
        self.assertEqual(rows[rejecting]["written_off"], 40.0)
        self.assertEqual(rows[rejecting]["back"], 0.0)
        self.assertTrue(trip._trip_report_weights_match(list(rows.values())))

    def test_a_later_trip_does_not_rewrite_an_earlier_sheet(self):
        delivery = self._delivery(5)
        first = self._trip(delivery)
        first.action_trip_load()
        first.action_depart()
        self.env["wizard.stock.picking.unbatch.undelivered"].create(
            {"picking_id": delivery.id, "reason_id": self.absent.id}
        ).action_confirm()
        first.write({"odometer_return": 1100.0, "fuel_return": 40.0})
        first.action_return()
        unload = first.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "unload"
        )
        unload.move_ids.picked = True
        unload.button_validate()
        before = self._rows(first)[delivery]

        second = self._trip(delivery)
        second.action_trip_load()
        second.action_depart()
        delivery.action_deliver()

        after = self._rows(first)[delivery]
        self.assertEqual(before["outcome"], after["outcome"])
        self.assertEqual((after["delivered"], after["back"]), (0.0, 100.0))
        self.assertEqual(self._rows(second)[delivery]["delivered"], 100.0)

    def test_a_loaded_delivery_does_not_leave_a_trip_before_unloading(self):
        kept, removed = self._delivery(5), self._delivery(2)
        trip = self._trip(kept | removed)
        trip.action_trip_load()

        with self.assertRaisesRegex(UserError, "Unload the trip first"):
            trip.write({"picking_ids": [Command.unlink(removed.id)]})
        with self.assertRaisesRegex(UserError, "Unload the trip first"):
            removed.batch_id = False

    def test_a_trip_unloaded_without_departing_sets_its_phone_results_aside(self):
        delivery = self._delivery(5)
        trip = self._trip(delivery)
        trip.action_trip_load()
        self._send(
            trip, self._chain(trip, [self._event("never-left", "deliver", delivery)])
        )
        self.assertEqual(trip.trip_offline_event_ids.state, "pending")

        trip.action_trip_unload()
        unload = trip.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "unload"
        )
        unload.move_ids.picked = True
        unload.button_validate()

        self.assertEqual(unload.state, "done")
        self.assertEqual(trip.trip_offline_event_ids.state, "dismissed")
        self.assertNotEqual(delivery.state, "done")

    def test_a_vehicle_loads_a_trip_only_once_it_is_empty(self):
        first = self._trip(self._delivery(5))
        first.action_trip_load()
        second = self._trip(self._delivery(2))

        with self.assertRaisesRegex(UserError, "still carries goods"):
            second.action_trip_load()

    def test_the_breakdown_time_is_when_it_happened(self):
        trip = self._trip(self._delivery(5))
        trip.action_trip_load()
        trip.action_depart()
        trip.date_departure = fields.Datetime.now() - timedelta(hours=2)
        wizard = self.env["wizard.stock.trip.handover"].create(
            {
                "batch_id": trip.id,
                "vehicle_id": self.rescue_vehicle.id,
                "operator_id": self.rescue_driver.id,
                "odometer_departure": 500.0,
                "fuel_departure": 60.0,
                "reason": "Engine failure",
                "breakdown_date": fields.Datetime.now() + timedelta(hours=1),
            }
        )
        with self.assertRaisesRegex(UserError, "breakdown time"):
            wizard.action_confirm()

        wizard.breakdown_date = fields.Datetime.now() - timedelta(minutes=45)
        rescue = self.env["stock.picking.batch"].browse(
            wizard.action_confirm()["res_id"]
        )

        breakdown = trip._trip_report_breakdown(rescue)
        self.assertEqual(breakdown.date, wizard.breakdown_date)
        self.assertGreater(rescue.date_departure, breakdown.date)
