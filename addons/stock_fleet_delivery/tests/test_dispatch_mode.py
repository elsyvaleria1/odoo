from freezegun import freeze_time

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestDispatchMode(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search([], limit=1)
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
        cls.out_type = cls.warehouse.out_type_id
        cls.out_type.write(
            {"dispatch_management": True, "dispatch_batch_required": True}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Freight", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 100
        )
        service = cls.env["product.product"].create(
            {"name": "Freight", "type": "service"}
        )
        cls.carriers = {
            mode: cls.env["delivery.carrier"].create(
                {
                    "name": mode,
                    "delivery_type": "fixed",
                    "product_id": service.id,
                    "dispatch_mode": mode,
                }
            )
            for mode in ("own_fleet", "salesperson", "third_party", "pickup")
        }

    def _picking(self, mode=None, location=None):
        location = location or self.stock_location
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "location_id": location.id,
                "location_dest_id": self.customer_location.id,
                "carrier_id": mode and self.carriers[mode].id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "location_id": location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.picked = True
        return picking

    def test_own_fleet_salesperson_and_no_carrier_travel_in_a_trip(self):
        for mode in (None, "own_fleet", "salesperson"):
            with self.subTest(mode=mode):
                picking = self._picking(mode)
                self.assertTrue(picking._requires_trip())
                with self.assertRaisesRegex(UserError, "must be delivered from a trip"):
                    picking.button_validate()

    def test_what_rides_our_vehicle_does_not_depend_on_the_type_rule(self):
        # The GPS asks what the vehicle carries even where trips are optional:
        # own fleet, salesperson and no mode ride it; a third-party carrier and
        # the customer do not. The type's rule only decides whether a trip is
        # compulsory, and only for what rides the vehicle.
        rides = {None: True, "own_fleet": True, "salesperson": True}
        rides |= {"third_party": False, "pickup": False}
        for compulsory in (True, False):
            self.out_type.dispatch_batch_required = compulsory
            for mode, expected in rides.items():
                with self.subTest(compulsory=compulsory, mode=mode):
                    picking = self._picking(mode)
                    self.assertEqual(picking._rides_trip_vehicle(), expected)
                    self.assertEqual(picking._requires_trip(), compulsory and expected)

    def _salesperson_trip(self, picking, tag):
        salesperson = self.env["res.users"].create(
            {
                "name": "Salesperson",
                "login": f"trip_salesperson_{tag}",
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("stock.group_stock_user").id,
                            self.env.ref("stock_fleet.group_trip_driver").id,
                        ]
                    )
                ],
            }
        )
        supervisor = self.env["res.users"].create(
            {
                "name": "Supervisor",
                "login": f"trip_supervisor_{tag}",
                "group_ids": [Command.set([self.env.ref("stock.group_stock_user").id])],
            }
        )
        kind = self.env.ref("resource.kind_vehicle")
        car = self.env["resource.resource"].create(
            {
                "name": "Salesperson's car",
                "kind_id": kind.id,
                "product_id": self.env["product.product"]
                .create({"name": "Car", "type": "consu", "asset_kind_id": kind.id})
                .id,
            }
        )
        trip = self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(picking.ids)],
                "vehicle_id": car.id,
                "operator_id": self.env["hr.employee"]
                .create({"name": "Salesperson", "user_id": salesperson.id})
                .id,
                "supervisor_id": supervisor.id,
                "odometer_departure": 1000.0,
            }
        )
        return trip, salesperson

    def test_a_salesperson_leaves_on_friday_and_delivers_on_monday(self):
        # Loaded on Friday at CDG, the salesperson takes the goods home for the
        # weekend and delivers on Monday: the trip stays open until then.
        for compulsory in (True, False):
            with self.subTest(compulsory=compulsory):
                self.out_type.dispatch_batch_required = compulsory
                picking = self._picking("salesperson")
                trip, salesperson = self._salesperson_trip(picking, compulsory)
                with freeze_time("2026-10-09 22:00:00"):
                    trip.with_user(salesperson).action_depart()
                self.assertEqual(trip.departed_uid, salesperson)
                with freeze_time("2026-10-11 12:00:00"):
                    trip._close_trip_at_last_stop()
                    self.assertEqual(trip.trip_state, "in_transit")
                    with self.assertRaisesRegex(UserError, "have no outcome"):
                        trip.action_return()
                with freeze_time("2026-10-12 17:00:00"):
                    picking.with_user(salesperson).action_deliver()
                self.assertEqual(picking.state, "done")
                self.assertEqual(trip.trip_state, "closed")
                self.assertEqual(
                    trip.date_return, fields.Datetime.to_datetime("2026-10-12 17:00")
                )

    def test_a_salesperson_does_not_bring_the_vehicle_back(self):
        for mode, returns in (
            (None, True),
            ("own_fleet", True),
            ("salesperson", False),
        ):
            with self.subTest(mode=mode):
                self.assertEqual(self._picking(mode)._trip_vehicle_returns(), returns)

    def test_a_third_party_carrier_needs_its_tracking_reference(self):
        picking = self._picking("third_party")
        self.assertFalse(picking._requires_trip())
        with self.assertRaisesRegex(UserError, "tracking reference"):
            picking.button_validate()
        picking.carrier_tracking_ref = "TG-123"
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_customer_pickup_does_not_travel_in_a_trip(self):
        picking = self._picking("pickup")
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_third_party_transit_sets_the_mode_when_the_carrier_does_not(self):
        transit = self.env["stock.location"].create(
            {
                "name": "Third-party transit",
                "usage": "transit",
                "dispatch_mode": "third_party",
            }
        )
        self.env["stock.quant"]._update_available_quantity(self.product, transit, 10)
        picking = self._picking(location=transit)
        self.assertEqual(picking._get_dispatch_mode(), "third_party")
        self.assertFalse(picking._rides_trip_vehicle())
        self.assertFalse(picking._requires_trip())
        with self.assertRaisesRegex(UserError, "tracking reference"):
            picking.button_validate()
        picking.carrier_tracking_ref = "TG-9"
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_the_carrier_mode_wins_over_the_location_mode(self):
        transit = self.env["stock.location"].create(
            {"name": "Transit", "usage": "transit", "dispatch_mode": "third_party"}
        )
        self.env["stock.quant"]._update_available_quantity(self.product, transit, 10)
        picking = self._picking("own_fleet", location=transit)
        self.assertTrue(picking._requires_trip())

    def test_a_third_party_parcel_may_stay_pending_when_the_trip_closes(self):
        kind = self.env.ref("resource.kind_vehicle")
        model = self.env["product.product"].create(
            {"name": "Van model", "type": "consu", "asset_kind_id": kind.id}
        )
        vehicle = self.env["resource.resource"].create(
            {"name": "Van", "kind_id": kind.id, "product_id": model.id}
        )
        parcel = self._picking("third_party")
        trip = self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(parcel.ids)],
                "vehicle_id": vehicle.id,
                "operator_id": self.env["hr.employee"].create({"name": "Driver"}).id,
                "supervisor_id": self.env.user.id,
                "odometer_departure": 1000.0,
            }
        )
        trip.action_depart()
        trip.odometer_return = 1040.0
        trip.action_return()
        self.assertEqual(trip.trip_state, "closed")
        self.assertEqual(
            parcel.state,
            "assigned",
            "The carrier delivers a parcel after the trip is back; the office "
            "validates it then, with its tracking reference.",
        )
