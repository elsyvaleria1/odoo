from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from .common import OfflineEventsMixin

# A standalone 1x1 transparent PNG, valid enough for the Image field to accept.
TEST_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY"
    "42YAAAAASUVORK5CYII="
)


@tagged("post_install", "-at_install")
class TestOfflineEvents(OfflineEventsMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.transit = cls.env["stock.location"].create(
            {
                "name": "Shipping transit",
                "usage": "transit",
                "location_id": cls.warehouse.view_location_id.id,
                "company_id": cls.warehouse.company_id.id,
            }
        )
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.write(
            {
                "dispatch_management": True,
                "dispatch_batch_required": True,
                "trip_trace": True,
            }
        )
        cls.supervisor = cls.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": "trace_supervisor",
                "group_ids": [
                    Command.set([cls.env.ref("stock.group_stock_manager").id])
                ],
            }
        )
        cls.driver_user = cls.env["res.users"].create(
            {
                "name": "Driver",
                "login": "trace_driver",
                "group_ids": [
                    Command.set([cls.env.ref("stock_fleet.group_trip_driver").id])
                ],
            }
        )
        cls.driver = cls.env["hr.employee"].create(
            {"name": "Driver", "user_id": cls.driver_user.id}
        )
        cls.rescue_driver = cls.env["hr.employee"].create({"name": "Rescue Driver"})
        kind = cls.env.ref("base.kind_vehicle")
        cls.model = cls.env["product.product"].create(
            {"name": "Test Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        cls.vehicle = cls.env["resource.resource"].create(
            {"name": "Truck", "kind_id": kind.id, "product_id": cls.model.id}
        )
        cls.rescue_vehicle = cls.env["resource.resource"].create(
            {"name": "Rescue Truck", "kind_id": kind.id, "product_id": cls.model.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Fertiliser", "is_storable": True, "weight": 20.0}
        )
        cls.lot_product = cls.env["product.product"].create(
            {
                "name": "Fungicide",
                "is_storable": True,
                "tracking": "lot",
                "weight": 1.0,
            }
        )
        cls.lot = cls.env["product.trace"].create(
            {"name": "L-001", "product_id": cls.lot_product.id}
        )
        Quant = cls.env["stock.quant"]
        Quant._update_available_quantity(cls.product, cls.stock_location, 1000)
        Quant._update_available_quantity(
            cls.lot_product, cls.stock_location, 1000, trace_id=cls.lot
        )
        cls.not_ordered = cls.env.ref("stock_fleet_trace.unbatch_reason_not_ordered")
        cls.damaged = cls.env.ref("stock_fleet_trace.unbatch_reason_damaged_product")
        cls.absent = cls.env.ref("stock_fleet.unbatch_reason_customer_absent")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _delivery(self, lines):
        """A delivery fed through the shipping transit, as CDG runs SHIP -> OUT.

        :param list lines: (product, quantity) pairs
        """
        delivery = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": self.env["res.partner"].create({"name": "Customer"}).id,
                "location_id": self.transit.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": product.id,
                            "product_uom_qty": quantity,
                            "location_id": self.transit.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                    for product, quantity in lines
                ],
            }
        )
        ship = self.env["stock.picking"].create(
            {
                "picking_type_id": self.warehouse.int_type_id.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.transit.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": move.product_id.id,
                            "product_uom_qty": move.product_uom_qty,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.transit.id,
                            "move_dest_ids": [Command.link(move.id)],
                        }
                    )
                    for move in delivery.move_ids
                ],
            }
        )
        delivery.action_confirm()
        ship.action_confirm()
        ship.action_assign()
        ship.move_ids.picked = True
        ship.button_validate()
        delivery.action_assign()
        self.assertEqual(delivery.state, "assigned")
        return delivery

    def _trip(self, pickings, **vals):
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(pickings.ids)],
                "vehicle_id": self.vehicle.id,
                "operator_id": self.driver.id,
                "supervisor_id": self.supervisor.id,
                "odometer_departure": 1000.0,
                "fuel_departure": 80.0,
                **vals,
            }
        )

    def _on_board(self, trip, product):
        quants = self.env["stock.quant"].search(
            [
                ("location_id", "in", trip.trip_location_ids.ids),
                ("product_id", "=", product.id),
            ]
        )
        return sum(quants.mapped("quantity"))

    def _return(self, trip):
        trip.write({"odometer_return": 1100.0, "fuel_return": 40.0})
        trip.action_return()

    def _checkpoint(self, trip, event_type):
        return trip.trip_checkpoint_ids.filtered(lambda c: c.event_type == event_type)

    # ------------------------------------------------------------------
    # Applying
    # ------------------------------------------------------------------
    def test_a_delivery_captured_offline_keeps_its_time_and_place(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()

        result = self._send(
            trip,
            self._event(
                "uuid-deliver",
                "deliver",
                delivery,
                receiver_name="Juan Perez",
                signature=TEST_PNG_B64,
            ),
        )

        self.assertEqual(result, {"uuid-deliver": {"state": "applied", "error": False}})
        self.assertEqual(delivery.state, "done")
        self.assertEqual(str(delivery.date_done), "2026-09-29 15:30:00")
        self.assertEqual(delivery.trip_receiver_name, "Juan Perez")
        self.assertTrue(delivery.signature)
        checkpoint = self._checkpoint(trip, "delivery")
        self.assertEqual(str(checkpoint.date), "2026-09-29 15:30:00")
        self.assertAlmostEqual(checkpoint.latitude, 20.6597)
        self.assertAlmostEqual(checkpoint.longitude, -103.3496)
        self.assertEqual(checkpoint.method, "manual")
        self.assertIn("uuid-deliver", checkpoint.note)
        self.assertEqual(checkpoint.user_id, self.driver_user)
        event = trip.trip_offline_event_ids
        self.assertEqual((event.state, event.user_id), ("applied", self.driver_user))
        self.assertTrue(event.event_hash)
        self.assertFalse(event.prev_hash)
        self.assertFalse(trip.trip_checkpoint_ids._check_chain())

    def test_an_event_sent_twice_is_applied_once(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        event = self._event("uuid-twice", "deliver", delivery)
        self._send(trip, event)

        result = self._send(trip, event, event)

        self.assertEqual(result["uuid-twice"]["state"], "applied")
        self.assertEqual(len(trip.trip_offline_event_ids), 1)
        self.assertEqual(len(self._checkpoint(trip, "delivery")), 1)

    def test_a_partial_delivery_captured_offline_flags_it_for_review(self):
        """The phone sends no quantities: the goods stay on board for the supervisor."""
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()

        result = self._send(
            trip,
            self._event(
                "uuid-partial",
                "partial",
                delivery,
                note="Customer took half, rest damaged",
                receiver_name="Juan Perez",
            ),
        )

        self.assertEqual(result["uuid-partial"]["state"], "applied", result)
        # Not validated: the vehicle still carries what it left with.
        self.assertEqual(delivery.state, "assigned")
        self.assertTrue(delivery.trip_partial_review)
        self.assertEqual(delivery.trip_receiver_name, "Juan Perez")
        self.assertEqual(self._on_board(trip, self.product), 5)
        self.assertTrue(
            any("Customer took half" in m.body for m in delivery.message_ids)
        )
        activity = delivery.activity_ids.filtered(
            lambda a: "Capture the partial delivery" in a.summary
        )
        self.assertEqual(activity.user_id, self.supervisor)

    def test_a_partial_delivery_without_a_note_goes_to_review(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()

        result = self._send(trip, self._event("uuid-no-note", "partial", delivery))

        self.assertEqual(result["uuid-no-note"]["state"], "review", result)
        self.assertIn("needs a note", result["uuid-no-note"]["error"])
        self.assertFalse(delivery.trip_partial_review)

    def test_the_partial_flag_blocks_the_unloading(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._send(
            trip, self._event("uuid-partial", "partial", delivery, note="Check it")
        )
        self.assertTrue(delivery.trip_partial_review)
        # The flag does not keep the trip itself from returning.
        self._return(trip)
        unload = trip.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "unload"
        )
        unload.move_ids.picked = True
        with self.assertRaisesRegex(UserError, "partial deliveries to capture"):
            unload.button_validate(skip_backorder=True)

    def test_the_partial_wizard_clears_the_review_flag(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._send(
            trip, self._event("uuid-partial", "partial", delivery, note="Check it")
        )
        self.assertTrue(delivery.trip_partial_review)

        wizard = (
            self.env["wizard.stock.trip.stop.result"]
            .with_context(default_picking_id=delivery.id)
            .create({})
        )
        wizard.action_confirm()

        self.assertFalse(delivery.trip_partial_review)
        self.assertEqual(delivery.state, "done")

    def test_a_stop_not_delivered_offline_leaves_the_trip(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()

        result = self._send(
            trip,
            self._event(
                "uuid-absent",
                "not_delivered",
                delivery,
                reason_id=self.absent.id,
                note="Gate closed",
            ),
        )

        self.assertEqual(result["uuid-absent"]["state"], "applied", result)
        self.assertFalse(delivery.batch_id)
        self.assertEqual(delivery.trip_delivery_result, "not_delivered")
        checkpoint = self._checkpoint(trip, "not_delivered")
        self.assertEqual(checkpoint.reason_id, self.absent)
        self.assertEqual(str(checkpoint.date), "2026-09-29 15:30:00")

    def test_a_failing_event_goes_to_review_and_blocks_the_trip(self):
        delivery = self._delivery([(self.product, 5)])
        stranger = self._delivery([(self.product, 1)])
        trip = self._trip(delivery)
        trip.action_depart()

        result = self._send(
            trip,
            self._event("uuid-bad", "deliver", stranger),
            self._event("uuid-good", "deliver", delivery),
        )

        self.assertEqual(result["uuid-bad"]["state"], "review")
        self.assertIn("is not a stop of trip", result["uuid-bad"]["error"])
        # One failure does not hold back the events after it.
        self.assertEqual(result["uuid-good"]["state"], "applied")
        self.assertEqual(stranger.state, "assigned")
        activity = trip.activity_ids.filtered(lambda a: "Offline event" in a.summary)
        self.assertEqual(activity.user_id, self.supervisor)
        self.assertEqual(trip.trip_offline_blocking_count, 1)
        with self.assertRaisesRegex(UserError, "resolve them first"):
            self._return(trip)

        bad = trip.trip_offline_event_ids.filtered(
            lambda e: e.client_uuid == "uuid-bad"
        )
        with self.assertRaisesRegex(UserError, "dismissed by its supervisor"):
            bad.with_user(self.driver_user).action_dismiss()
        bad.with_user(self.supervisor).action_dismiss()
        self.assertEqual(bad.state, "dismissed")
        self._return(trip)
        self.assertEqual(trip.trip_state, "closed")

    def test_a_pending_event_blocks_the_unloading(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._send(
            trip,
            self._event(
                "uuid-refused", "not_delivered", delivery, reason_id=self.absent.id
            ),
        )
        self._return(trip)
        # The phone syncs after the trip closed: nothing left to deliver.
        self._send(trip, self._event("uuid-late", "deliver", delivery))
        unload = trip.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "unload"
        )
        unload.move_ids.picked = True
        with self.assertRaisesRegex(UserError, "resolve them first"):
            unload.button_validate(skip_backorder=True)

    def test_scans_captured_offline_mark_arrival_and_count_lots(self):
        delivery = self._delivery([(self.lot_product, 3)])
        trip = self._trip(delivery)
        trip.action_depart()

        result = self._send(
            trip,
            self._event("uuid-slip", "scan", code=delivery.name),
            # The slip already counted every unit; the lot label only checks it.
            self._event("uuid-lot", "scan", delivery, code=self.lot.name),
            self._event("uuid-done", "deliver", delivery),
        )

        self.assertEqual(
            {uuid: value["state"] for uuid, value in result.items()},
            dict.fromkeys(("uuid-slip", "uuid-lot", "uuid-done"), "applied"),
            result,
        )
        arrival = self._checkpoint(trip, "arrival")
        self.assertEqual(arrival.method, "manual")
        self.assertEqual(str(arrival.date), "2026-09-29 15:30:00")
        self.assertEqual(delivery.trip_scan_ids.mapped("kind"), ["lot", "delivery"])
        self.assertEqual(delivery.state, "done")

    def test_an_incident_captured_offline_waits_for_review(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()

        self._send(
            trip,
            self._event(
                "uuid-spill",
                "incident",
                incident={
                    "incident_type": "spill",
                    "description": "Bag torn",
                    "lines": [{"product_id": self.product.id, "quantity": 1}],
                },
            ),
        )

        incident = trip.trip_incident_ids
        self.assertEqual(incident.state, "reported")
        self.assertEqual(str(incident.date), "2026-09-29 15:30:00")
        self.assertEqual(incident.line_ids.quantity, 1)
        self.assertEqual(self._checkpoint(trip, "incident").method, "manual")

    # ------------------------------------------------------------------
    # Phone hash chain
    # ------------------------------------------------------------------
    def test_a_tampered_event_goes_to_review_and_breaks_the_chain(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        event = self._event("uuid-tampered", "deliver", delivery)
        self._chain(trip, [event])
        # Altered after the phone hashed it: the hash no longer matches the data.
        event["latitude"] = 0.0

        result = self._send(trip, event, chain=False)

        self.assertEqual(result["uuid-tampered"]["state"], "review", result)
        self.assertIn("was altered", result["uuid-tampered"]["error"])
        self.assertTrue(trip.trip_offline_chain_broken)
        activity = trip.activity_ids.filtered(lambda a: "do not verify" in a.summary)
        self.assertEqual(activity.user_id, self.supervisor)

    def test_a_gap_in_the_chain_goes_to_review_and_breaks_it(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        first = self._event("uuid-first", "scan", code=trip.name)
        second = self._event("uuid-second", "deliver", delivery)
        self._chain(trip, [first, second])
        # The phone lost "first": "second" chains to a hash the trip never saw.
        second["prev_hash"] = "not-a-real-hash"
        second["event_hash"] = self.env["stock.trip.offline.event"]._trip_hash_event(
            second
        )

        result = self._send(trip, second, chain=False)

        self.assertEqual(result["uuid-second"]["state"], "review", result)
        self.assertIn("breaks the chain", result["uuid-second"]["error"])
        self.assertTrue(trip.trip_offline_chain_broken)

    def test_an_event_with_no_hash_goes_to_review_and_breaks_the_chain(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()

        result = self._send(
            trip, self._event("uuid-unhashed", "deliver", delivery), chain=False
        )

        self.assertEqual(result["uuid-unhashed"]["state"], "review", result)
        self.assertIn("cannot be verified", result["uuid-unhashed"]["error"])
        self.assertTrue(trip.trip_offline_chain_broken)

    def test_a_phone_head_ahead_of_what_was_received_blocks_the_return(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._send(trip, self._event("uuid-deliver", "deliver", delivery))

        # The phone still holds an event beyond the last one the trip received.
        self._send(trip, head="a-later-hash-the-trip-never-received")
        with self.assertRaisesRegex(UserError, "unsent events"):
            self._return(trip)

        # Once the phone's head matches what the trip has, it returns.
        self._send(trip, head=trip._trip_last_event_hash())
        self._return(trip)
        self.assertEqual(trip.trip_state, "closed")

    # ------------------------------------------------------------------
    # The package the phone downloads
    # ------------------------------------------------------------------
    def test_the_package_lists_the_stops_in_route_order(self):
        first = self._delivery([(self.product, 5)])
        second = self._delivery([(self.lot_product, 2)])
        trip = self._trip(first | second)
        second.batch_sequence = 0
        first.batch_sequence = 1
        second.partner_id.write({"partner_latitude": 20.5, "partner_longitude": -103.4})
        trip.action_depart()

        package = trip.with_user(self.driver_user)._trip_offline_package()

        self.assertEqual(package["trip"]["name"], trip.name)
        self.assertEqual(
            [stop["picking_id"] for stop in package["stops"]], [second.id, first.id]
        )
        stop = package["stops"][0]
        self.assertEqual(stop["latitude"], 20.5)
        self.assertEqual(
            [(line["lot"], line["quantity"]) for line in stop["lines"]],
            [(self.lot.name, 2)],
        )
        reasons = {
            reason["id"]: reason["scope"] for reason in package["unbatch_reasons"]
        }
        # A stop not delivered takes a reason for the whole delivery.
        self.assertNotIn(self.not_ordered.id, reasons)
        self.assertIn(self.absent.id, reasons)
        self.assertIn("spill", [t["code"] for t in package["incident_types"]])
        self.assertTrue(package["server_time"])

    def test_only_the_driver_supervisor_or_a_manager_syncs_the_trip(self):
        trip = self._trip(self._delivery([(self.product, 1)]))
        other = self.env["res.users"].create(
            {
                "name": "Other driver",
                "login": "offline_other_driver",
                "group_ids": [
                    Command.set([self.env.ref("stock_fleet.group_trip_driver").id])
                ],
            }
        )
        with self.assertRaises(AccessError):
            trip.with_user(other)._trip_offline_package()
        with self.assertRaises(AccessError):
            self._send(trip, user=other)
        self.assertTrue(trip.with_user(self.supervisor)._trip_offline_package())
