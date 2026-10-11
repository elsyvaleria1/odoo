from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTripTrace(TransactionCase):
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

    def _stop_result(self, picking, delivered, reason=None, whole_reason=None):
        """Record a stop: ``delivered`` maps products to the quantity taken."""
        wizard = (
            self.env["wizard.stock.trip.stop.result"]
            .with_context(default_picking_id=picking.id)
            .create({"reason_id": whole_reason.id if whole_reason else False})
        )
        for line in wizard.line_ids:
            line.qty_delivered = delivered.get(line.product_id, line.qty_on_board)
            if line.qty_rejected:
                line.reason_id = reason
        wizard.action_confirm()

    def _return(self, trip):
        trip.write({"odometer_return": 1100.0, "fuel_return": 40.0})
        trip.action_return()

    def _confirm_unload(self, trip, counted=None):
        """The warehouse counts the unloading; ``counted`` overrides per product."""
        unload = trip.trip_support_picking_ids.filtered(
            lambda p: p.trip_support_kind == "unload"
        )
        for move in unload.move_ids:
            if counted and move.product_id in counted:
                move.move_line_ids.quantity = counted[move.product_id]
            move.picked = True
        unload.button_validate(skip_backorder=True, cancel_backorder_ids=unload.ids)
        return unload

    def _dump(self, trip):
        return "; ".join(
            f"{b.product_id.name}/{b.trace_id.name or '-'}: loaded {b.qty_loaded} "
            f"recv {b.qty_received} deliv {b.qty_delivered} off {b.qty_written_off} "
            f"handed {b.qty_handed_over} back {b.qty_returned} diff {b.qty_difference}"
            for b in trip.trip_balance_ids
        )

    def _balance(self, trip, product):
        return trip.trip_balance_ids.filtered(lambda line: line.product_id == product)

    # ------------------------------------------------------------------
    # Loading and departure
    # ------------------------------------------------------------------
    def test_departure_loads_the_goods_onto_the_vehicle(self):
        delivery = self._delivery([(self.product, 5), (self.lot_product, 3)])
        trip = self._trip(delivery)
        trip.action_depart()

        self.assertTrue(trip.date_loaded)
        self.assertEqual(trip.trip_state, "in_transit")
        vehicle_location = trip.trip_location_ids
        self.assertEqual(vehicle_location.location_id, self.transit)
        self.assertEqual(self._on_board(trip, self.product), 5)
        self.assertEqual(self._on_board(trip, self.lot_product), 3)
        # The delivery still holds its goods, now on the vehicle, same lot.
        self.assertEqual(delivery.state, "assigned")
        lines = delivery.move_ids.move_line_ids
        self.assertEqual(lines.location_id, vehicle_location)
        self.assertEqual(
            lines.filtered(lambda ml: ml.product_id == self.lot_product).trace_id,
            self.lot,
        )
        self.assertEqual(
            set(delivery.move_ids.move_orig_ids.mapped("trip_move_kind")), {"load"}
        )
        self.assertEqual(trip.weight_departure, 5 * 20.0 + 3 * 1.0)
        self.assertEqual(
            trip.trip_checkpoint_ids.mapped("event_type"), ["load", "departure"]
        )

    def test_a_trip_takes_stock_to_sell_and_brings_back_the_rest(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        wizard = self.env["wizard.stock.trip.load.stock"].create(
            {
                "batch_id": trip.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "quantity": 10})
                ],
            }
        )
        wizard.action_load()

        self.assertTrue(trip.date_loaded)
        self.assertEqual(self._on_board(trip, self.product), 15)
        trip.action_depart()
        delivery.action_deliver()
        self._return(trip)
        self._confirm_unload(trip)

        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))
        line = self._balance(trip, self.product)
        self.assertEqual(
            (line.qty_loaded, line.qty_delivered, line.qty_returned), (15, 5, 10)
        )

    def test_stock_on_board_is_not_reserved_by_the_warehouse(self):
        seed = self.env["product.product"].create({"name": "Seed", "is_storable": True})
        self.env["stock.quant"]._update_available_quantity(
            seed, self.stock_location, 10
        )
        trip = self._trip(self._delivery([(self.product, 5)]))
        trip._trip_load_free_stock([(seed, 10)])

        counter = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": seed.id,
                            "product_uom_qty": 4,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        counter.action_confirm()
        counter.action_assign()

        self.assertEqual(counter.move_ids.quantity, 0)
        self.assertEqual(self._on_board(trip, seed), 10)

    def test_stock_to_sell_must_be_in_the_warehouse(self):
        trip = self._trip(self._delivery([(self.product, 5)]))
        with self.assertRaisesRegex(UserError, "does not hold all"):
            trip._trip_load_free_stock([(self.product, 100000)])

    def test_departure_requires_the_fuel(self):
        trip = self._trip(self._delivery([(self.product, 1)]), fuel_departure=0.0)
        with self.assertRaisesRegex(UserError, "Fuel at departure"):
            trip.action_depart()
        self.assertFalse(trip.date_loaded)

    def test_a_loaded_trip_takes_no_new_delivery(self):
        trip = self._trip(self._delivery([(self.product, 1)]))
        trip.action_trip_load()
        self.assertEqual(trip.trip_state, "loaded")
        other = self._delivery([(self.product, 1)])
        with self.assertRaisesRegex(UserError, "already loaded"):
            trip.write({"picking_ids": [Command.link(other.id)]})
        with self.assertRaisesRegex(UserError, "already loaded"):
            other.with_context(trip_handover=True).write({"batch_id": trip.id})

    # ------------------------------------------------------------------
    # Stops
    # ------------------------------------------------------------------
    def test_a_full_trip_balances_without_unloading(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        delivery.action_deliver()
        self._return(trip)

        self.assertFalse(trip.unload_picking_id)
        self.assertEqual(trip.trip_state, "closed")
        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))
        line = self._balance(trip, self.product)
        self.assertEqual((line.qty_loaded, line.qty_delivered), (5, 5))

    def test_a_refused_product_comes_back_to_stock(self):
        delivery = self._delivery([(self.product, 5), (self.lot_product, 3)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._stop_result(delivery, {self.product: 3}, reason=self.not_ordered)

        self.assertEqual(delivery.state, "done")
        self.assertEqual(delivery.trip_delivery_result, "partial")
        self.assertFalse(
            delivery.backorder_ids, "a refusal for good leaves nothing pending"
        )
        self.assertEqual(self._on_board(trip, self.product), 2)
        rejection = trip.trip_checkpoint_ids.filtered(
            lambda c: c.event_type == "rejection"
        )
        self.assertEqual(
            (rejection.product_id, rejection.quantity, rejection.reason_id),
            (self.product, 2, self.not_ordered),
        )

        self._return(trip)
        self.assertEqual(trip.trip_state, "returned")
        self.assertEqual(trip.balance_state, "pending", self._dump(trip))
        unload = self._confirm_unload(trip)
        self.assertEqual(unload.move_ids.location_dest_id, self.stock_location)
        self.assertEqual(trip.trip_state, "closed")
        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))
        line = self._balance(trip, self.product)
        self.assertEqual(
            (line.qty_loaded, line.qty_delivered, line.qty_returned), (5, 3, 2)
        )

    def test_a_damaged_product_leaves_a_backorder_that_does_not_reuse_it(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._stop_result(delivery, {self.product: 3}, reason=self.damaged)

        backorder = delivery.backorder_ids
        self.assertEqual(backorder.move_ids.product_uom_qty, 2)
        self.assertFalse(backorder.batch_id)
        # The rejected units are free on the vehicle: they return to stock, not to
        # the customer.
        self.assertFalse(backorder.move_ids.move_line_ids)
        self._return(trip)
        self._confirm_unload(trip)
        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))

    def test_an_absent_customer_keeps_the_goods_reserved_for_the_next_trip(self):
        delivery = self._delivery([(self.product, 4)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._stop_result(delivery, {self.product: 0}, whole_reason=self.absent)

        self.assertFalse(delivery.batch_id)
        self.assertEqual(delivery.trip_delivery_result, "not_delivered")
        self._return(trip)
        unload = self._confirm_unload(trip)
        # Back to where deliveries leave from, still reserved to the delivery.
        self.assertEqual(unload.move_ids.location_dest_id, self.transit)
        self.assertEqual(delivery.state, "assigned")
        self.assertEqual(delivery.move_ids.move_line_ids.location_id, self.transit)
        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))

    def test_a_short_count_on_unloading_shows_a_difference(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        self._stop_result(delivery, {self.product: 3}, reason=self.not_ordered)
        self._return(trip)
        self._confirm_unload(trip, counted={self.product: 1})

        self.assertEqual(trip.balance_state, "difference", self._dump(trip))
        self.assertEqual(self._balance(trip, self.product).qty_difference, -1)

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------
    def test_a_spill_writes_off_only_once_approved(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        incident = self.env["stock.trip.incident"].create(
            {
                "batch_id": trip.id,
                "incident_type": "spill",
                "description": "A sack broke on the road",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 2,
                            "picking_id": delivery.id,
                        }
                    )
                ],
            }
        )
        self.assertEqual(self._on_board(trip, self.product), 5)
        incident.with_user(self.supervisor).action_approve()
        self.assertEqual(incident.state, "approved")
        self.assertEqual(incident.scrap_ids.scrap_qty, 2)
        self.assertEqual(self._on_board(trip, self.product), 3)

        self._stop_result(delivery, {})
        self.assertEqual(delivery.backorder_ids.move_ids.product_uom_qty, 2)
        self._return(trip)
        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))
        line = self._balance(trip, self.product)
        self.assertEqual(
            (line.qty_loaded, line.qty_delivered, line.qty_written_off), (5, 3, 2)
        )

    def test_only_the_supervisor_or_a_manager_reviews_an_incident(self):
        trip = self._trip(self._delivery([(self.product, 1)]))
        trip.action_depart()
        clerk = self.env["res.users"].create(
            {
                "name": "Clerk",
                "login": "trace_clerk",
                "group_ids": [Command.set([self.env.ref("stock.group_stock_user").id])],
            }
        )
        incident = self.env["stock.trip.incident"].create(
            {"batch_id": trip.id, "incident_type": "other", "description": "Flat tyre"}
        )
        with self.assertRaisesRegex(UserError, "reviewed by"):
            incident.with_user(clerk).action_approve()

    def test_a_breakdown_hands_the_load_to_a_rescue_vehicle(self):
        delivered = self._delivery([(self.product, 2)])
        pending = self._delivery([(self.product, 5)])
        trip = self._trip(delivered | pending)
        trip.action_depart()
        delivered.action_deliver()

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
        rescue = self.env["stock.picking.batch"].browse(action["res_id"])
        self.assertEqual(pending.batch_id, rescue)
        self.assertEqual(delivered.batch_id, trip)
        self.assertEqual(rescue.trip_state, "in_transit")
        self.assertEqual(self._on_board(trip, self.product), 0)
        self.assertEqual(self._on_board(rescue, self.product), 5)

        pending.action_deliver()
        self._return(trip)
        self._return(rescue)
        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))
        self.assertEqual(rescue.balance_state, "balanced", self._dump(rescue))
        self.assertEqual(self._balance(trip, self.product).qty_handed_over, 5)
        self.assertEqual(self._balance(rescue, self.product).qty_received, 5)
        self.assertEqual(self._balance(rescue, self.product).qty_delivered, 5)

    def test_the_driver_records_the_route_with_driver_rights_only(self):
        delivery = self._delivery([(self.product, 5)])
        trip = self._trip(delivery)
        trip.action_depart()
        as_driver = self.env(user=self.driver_user)
        stop = delivery.with_env(as_driver)
        stop.action_trip_arrived()
        self._stop_result(stop, {self.product: 4}, reason=self.not_ordered)
        incident = (
            self.env["stock.trip.incident"]
            .with_user(self.driver_user)
            .create(
                {
                    "batch_id": trip.id,
                    "incident_type": "fuel",
                    "fuel_liters": 30.0,
                    "description": "Refuelled on the highway",
                }
            )
        )
        with self.assertRaisesRegex(UserError, "reviewed by"):
            incident.action_approve()
        trip_as_driver = trip.with_env(as_driver)
        trip_as_driver.write({"odometer_return": 1100.0, "fuel_return": 40.0})
        trip_as_driver.action_return()
        self.assertEqual(
            trip.trip_checkpoint_ids.mapped("event_type"),
            [
                "load",
                "departure",
                "arrival",
                "delivery",
                "rejection",
                "incident",
                "return",
            ],
        )
        self.assertEqual(
            set(trip.trip_checkpoint_ids.mapped("user_id")) - {self.env.user},
            {self.driver_user},
        )

    def test_the_driver_records_a_refusal_on_a_sale_without_sales_rights(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "warehouse_id": self.warehouse.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "product_qty": 5})
                ],
            }
        )
        order.action_confirm()
        # A warehouse in two steps stages the goods first.
        for leg in order.picking_ids.filtered(
            lambda p: p.picking_type_id != self.out_type
        ):
            leg.action_assign()
            leg.move_ids.picked = True
            leg.button_validate()
        delivery = order.picking_ids.filtered(
            lambda p: p.picking_type_id == self.out_type
        )
        delivery.action_assign()
        trip = self._trip(delivery)
        trip.action_depart()
        stop = delivery.with_env(self.env(user=self.driver_user))
        self._stop_result(stop, {self.product: 3}, reason=self.not_ordered)
        self.assertEqual(delivery.trip_delivery_result, "partial")
        self.assertEqual(delivery.move_ids.quantity, 3)

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------
    def test_scanning_departs_marks_arrival_and_counts_the_lots(self):
        delivery = self._delivery([(self.product, 5), (self.lot_product, 3)])
        trip = self._trip(delivery)
        trip.action_trip_load()
        as_driver = trip.with_user(self.driver_user)
        with self.assertRaisesRegex(UserError, "not by its operator"):
            as_driver._trip_process_scan(trip.name)

        # The supervisor (or the gate) reads the sheet; the driver cannot.
        message, _stop = trip.with_user(self.supervisor)._trip_process_scan(trip.name)
        self.assertEqual(trip.trip_state, "in_transit", message)
        departure = trip.trip_checkpoint_ids.filtered(
            lambda c: c.event_type == "departure"
        )
        self.assertEqual(departure.method, "barcode")

        _message, stop = as_driver._trip_process_scan(delivery.name)
        self.assertEqual(stop, delivery)
        self.assertTrue(delivery.trip_arrival_date)
        # One scan of the slip registers every unit of the delivery.
        scanned = delivery._trip_scanned_by_lot()
        self.assertEqual(scanned[(self.lot_product, self.lot)], 3)
        self.assertEqual(scanned[(self.product, self.env["product.trace"])], 5)
        with self.assertRaisesRegex(UserError, "does not travel"):
            other = self.env["product.trace"].create(
                {"name": "OTHER-LOT", "product_id": self.lot_product.id}
            )
            as_driver._trip_process_scan(other.name, picking=delivery)
        # A lot read afterwards only checks it: it is already complete.
        message, _stop = as_driver._trip_process_scan(self.lot.name, picking=delivery)
        self.assertIn("already complete", message)
        self.assertEqual(
            delivery._trip_scanned_by_lot()[(self.lot_product, self.lot)], 3
        )
        delivery.with_user(self.driver_user).action_deliver()
        self.assertEqual(delivery.state, "done")

    def test_one_lot_scan_counts_the_whole_lot(self):
        delivery = self._delivery([(self.product, 5), (self.lot_product, 3)])
        trip = self._trip(delivery)
        trip.action_depart()
        as_driver = trip.with_user(self.driver_user)
        message, _stop = as_driver._trip_process_scan(self.lot.name, picking=delivery)
        self.assertIn("3", message)
        self.assertEqual(
            delivery._trip_scanned_by_lot()[(self.lot_product, self.lot)], 3
        )
        # The product without lot was not counted, so it does not block Delivered.
        delivery.with_user(self.driver_user).action_deliver()
        self.assertEqual(delivery.state, "done")

    def test_a_short_lot_count_still_asks_for_partial(self):
        delivery = self._delivery([(self.product, 5), (self.lot_product, 3)])
        trip = self._trip(delivery)
        trip.action_depart()
        as_driver = trip.with_user(self.driver_user)
        # An explicit count (e.g. the office typing what the customer took).
        as_driver._trip_process_scan(self.lot.name, 2, delivery)
        with self.assertRaisesRegex(UserError, "only 3.0 travel"):
            as_driver._trip_process_scan(self.lot.name, 2, delivery)
        with self.assertRaisesRegex(UserError, "does not match"):
            delivery.with_user(self.driver_user).action_deliver()
        wizard = (
            self.env["wizard.stock.trip.stop.result"]
            .with_context(default_picking_id=delivery.id)
            .create({})
        )
        proposed = {line.product_id: line.qty_delivered for line in wizard.line_ids}
        self.assertEqual(proposed, {self.lot_product: 2, self.product: 0})

    def test_any_validation_on_the_route_leaves_its_checkpoint(self):
        delivery = self._delivery([(self.product, 2)])
        trip = self._trip(delivery)
        trip.action_depart()
        delivery.move_ids.picked = True
        delivery.button_validate()  # e.g. from the barcode app
        outcome = trip.trip_checkpoint_ids.filtered(
            lambda c: c.event_type == "delivery"
        )
        self.assertEqual(outcome.picking_id, delivery)
        self.assertEqual(delivery.trip_delivery_result, "complete")

    def test_an_expired_lot_does_not_board_without_an_approver(self):
        if "block_expired_lots" not in self.out_type._fields:
            self.skipTest("stock_expired_lot_guard is not installed")
        self.out_type.block_expired_lots = True
        # A one-step delivery: it draws straight from the warehouse stock.
        delivery = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": self.env["res.partner"].create({"name": "Buyer"}).id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.lot_product.id,
                            "product_uom_qty": 3,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        delivery.action_confirm()
        delivery.action_assign()
        # The lot expires after the reservation, as it would overnight.
        self.lot.expiration_date = "2020-01-01 00:00:00"
        trip = self._trip(delivery)
        with self.assertRaisesRegex(UserError, "expired"):
            trip.action_trip_load()
        self.assertFalse(trip.date_loaded)

    def test_a_lot_past_its_removal_date_boards_without_an_unseen_question(self):
        # Past its removal date but not expired: the expiry wizard would ask on
        # the loading transfer and, unanswered, leave the trip loaded with
        # nothing on board. The expired-lot guard already judged the delivery.
        if "use_expiration_date" not in self.lot_product._fields:
            self.skipTest("product_expiry is not installed")
        self.lot_product.use_expiration_date = True
        delivery = self._delivery([(self.lot_product, 3)])
        # The removal date passes after the reservation, as it would overnight.
        now = fields.Datetime.now()
        self.lot.write(
            {
                "expiration_date": now + timedelta(days=24),
                "removal_date": now - timedelta(days=1),
            }
        )
        trip = self._trip(delivery)
        trip.action_trip_load()
        self.assertTrue(trip.date_loaded)
        self.assertEqual(set(trip.trip_support_picking_ids.mapped("state")), {"done"})
        self.assertEqual(self._on_board(trip, self.lot_product), 3)
        trip.action_depart()
        self.assertEqual(trip.trip_state, "in_transit")
        # Nor is the question asked again at the customer's door, where the
        # expired-lot guard already judged the lot on loading.
        if "block_expired_lots" in self.out_type._fields:
            self.out_type.block_expired_lots = True
            self.assertTrue(delivery._trip_expiry_decided())
            delivery.with_user(self.driver_user).action_deliver()
            self.assertEqual(delivery.state, "done")

    def test_without_the_expired_lot_guard_the_door_still_asks(self):
        delivery = self._delivery([(self.product, 1)])
        trip = self._trip(delivery)
        trip.action_trip_load()
        trip.action_depart()
        if "block_expired_lots" in self.out_type._fields:
            self.out_type.block_expired_lots = False
        self.assertFalse(delivery._trip_expiry_decided())

    def test_the_delivery_slip_names_the_driver_and_who_received(self):
        self.env.ref("product.decimal_stock_weight").digits = 6
        self.product.weight = 1.25
        delivery = self._delivery([(self.product, 2)])
        # The slip prints in the customer's language: English here, whatever
        # languages the database has.
        delivery.partner_id.lang = "en_US"
        trip = self._trip(delivery)
        trip.action_depart()
        delivery.action_deliver()
        report = self.env["ir.actions.report"]
        html = report._render_qweb_html("stock.report_deliveryslip", delivery.ids)[
            0
        ].decode()
        # Operator is the trip's driver, and a delivery without a phone signature
        # gets blank lines to sign on paper, not the customer's name.
        self.assertIn(self.driver.name, html)
        # The company keeps weights at six decimals (marin); the slip prints two.
        self.assertIn("2.50", html)
        self.assertNotIn("2.500", html)
        self.assertIn("Received By", html)
        self.assertIn("______", html)
        delivery.trip_receiver_name = "Juan Almacenista"
        html = report._render_qweb_html("stock.report_deliveryslip", delivery.ids)[
            0
        ].decode()
        self.assertIn("Juan Almacenista", html)
        # In Spanish, as production prints it, the paper lines are translated.
        Lang = self.env["res.lang"].with_context(active_test=False)
        if not Lang.search([("code", "=", "es_MX"), ("active", "=", True)]):
            return
        delivery.partner_id.lang = "es_MX"
        delivery.trip_receiver_name = False
        html = report._render_qweb_html("stock.report_deliveryslip", delivery.ids)[
            0
        ].decode()
        self.assertIn("Recibió:", html)
        self.assertIn("Firma:", html)
        self.assertNotIn("Signature:", html)

    def test_a_delivery_on_board_comes_off_only_as_not_delivered(self):
        # Taking a loaded delivery off the trip as it is would trap its goods on
        # the vehicle: the unload would not bring them back.
        delivery = self._delivery([(self.product, 2)])
        trip = self._trip(delivery)
        trip.action_trip_load()
        trip.action_depart()
        with self.assertRaisesRegex(UserError, "register them as not delivered"):
            delivery._take_off_trip_as_correction("credit held")
        self.assertEqual(delivery.batch_id, trip)

    def test_a_third_party_delivery_does_not_board(self):
        if "dispatch_mode" not in self.transit._fields:
            self.skipTest("stock_fleet_delivery is not installed")
        ours = self._delivery([(self.product, 1)])
        carrier = self._delivery([(self.product, 1)])
        carrier.location_id.dispatch_mode = "third_party"
        self.assertFalse(carrier._requires_trip())
        trip = self._trip(ours | carrier)
        with self.assertRaisesRegex(UserError, carrier.name):
            trip.action_trip_load()
        self.assertFalse(trip.date_loaded)

    def test_a_breakdown_after_an_approved_spill_hands_over_the_rest(self):
        self._spill_then_breakdown("direct")

    def test_a_spill_does_not_hold_back_a_deliver_all_at_once_delivery(self):
        # Production creates every delivery as "deliver all at once": once
        # loaded, a spill must not keep the rescue trip from departing.
        self._spill_then_breakdown("one")

    def test_a_trip_of_a_type_that_does_not_require_trips_says_so(self):
        self.out_type.dispatch_batch_required = False
        trip = self._trip(self._delivery([(self.product, 1)]))
        with self.assertRaisesRegex(UserError, "Deliver in"):
            trip.action_trip_load()
        self.assertFalse(trip.date_loaded)

    def _spill_then_breakdown(self, move_type):
        spilled = self._delivery([(self.product, 5)])
        other = self._delivery([(self.product, 2)])
        (spilled | other).move_type = move_type
        self.assertEqual(spilled.state, "assigned")
        trip = self._trip(spilled | other)
        trip.action_depart()
        incident = self.env["stock.trip.incident"].create(
            {
                "batch_id": trip.id,
                "incident_type": "spill",
                "description": "A sack broke on the road",
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "picking_id": spilled.id,
                        }
                    )
                ],
            }
        )
        incident.with_user(self.supervisor).action_approve()
        self.assertEqual(spilled.state, "assigned")

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
        rescue = self.env["stock.picking.batch"].browse(action["res_id"])
        self.assertEqual(rescue.trip_state, "in_transit")
        self.assertEqual((spilled | other).batch_id, rescue)
        self.assertEqual(self._on_board(rescue, self.product), 6)

        self._stop_result(spilled, {})
        other.action_deliver()
        self._return(trip)
        self._return(rescue)
        self.assertEqual(trip.balance_state, "balanced", self._dump(trip))
        self.assertEqual(rescue.balance_state, "balanced", self._dump(rescue))

    # ------------------------------------------------------------------
    # The log
    # ------------------------------------------------------------------
    def test_the_log_cannot_be_edited_and_tampering_is_detected(self):
        trip = self._trip(self._delivery([(self.product, 1)]))
        trip.action_depart()
        checkpoint = trip.trip_checkpoint_ids[:1]
        with self.assertRaises(UserError):
            checkpoint.write({"note": "edited"})
        with self.assertRaises(UserError):
            checkpoint.unlink()
        trip.action_trip_verify_log()
        # An edit made behind the ORM breaks the seal.
        self.env.cr.execute(
            "UPDATE stock_trip_checkpoint SET odometer = 1 WHERE id = %s",
            [checkpoint.id],
        )
        checkpoint.invalidate_recordset()
        with self.assertRaisesRegex(UserError, "altered"):
            trip.action_trip_verify_log()
