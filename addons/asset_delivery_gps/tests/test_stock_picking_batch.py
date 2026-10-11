from datetime import timedelta

from odoo import Command, fields
from odoo.exceptions import UserError

from .common import GpsBridgeCase


class TestTripGpsOdometer(GpsBridgeCase):
    def _trip(self):
        vehicle = self.env["resource.asset.vehicle"].browse(self.asset.id)
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.warehouse.out_type_id.id,
                "vehicle_id": vehicle.id,
            }
        )

    def test_the_departure_odometer_is_read_from_the_gps(self):
        self.device.log_gps_last_id = self.gps_log(15000.0)
        trip = self._trip()
        trip.action_read_gps_odometer_departure()
        self.assertEqual(trip.odometer_departure, 15000.0)

    def test_a_trip_without_a_vehicle_asks_for_one(self):
        trip = self._trip()
        trip.vehicle_id = False
        with self.assertRaisesRegex(UserError, "has no vehicle"):
            trip.action_read_gps_odometer_departure()

    def test_a_stale_reading_asks_for_manual_entry(self):
        self.device.log_gps_last_id = self.gps_log(15000.0, days_ago=400)
        trip = self._trip()
        with self.assertRaises(UserError):
            trip.action_read_gps_odometer_departure()


class TestTripGpsLegs(GpsBridgeCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.out_type = cls.warehouse.out_type_id
        cls.stock = cls.warehouse.lot_stock_id
        cls.customers = cls.env.ref("stock.stock_location_customers")
        cls.product = cls.env["product.product"].create(
            {"name": "Freight", "is_storable": True}
        )
        cls.env["stock.quant"]._update_available_quantity(cls.product, cls.stock, 10)
        cls.t0 = fields.Datetime.to_datetime("2026-09-28 08:00:00")

    def _at(self, minutes):
        return self.t0 + timedelta(minutes=minutes)

    def _log(self, minutes, odometer=0.0, latitude=19.26, longitude=-99.6):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": self._at(minutes),
                "latitude": latitude,
                "longitude": longitude,
                "odometer": odometer,
                "odometer_valid": bool(odometer),
            }
        )

    def _loaded(self, trip):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "location_id": self.stock.id,
                "location_dest_id": self.customers.id,
                "batch_id": trip.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": 1,
                            "location_id": self.stock.id,
                            "location_dest_id": self.customers.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _deliver(self, picking, minutes):
        picking.move_ids.picked = True
        picking.button_validate()
        picking.date_done = self._at(minutes)

    def _trip(self):
        return self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "vehicle_id": self.env["resource.asset.vehicle"]
                .browse(self.asset.id)
                .id,
            }
        )

    def test_each_delivery_gets_the_kilometres_of_its_leg(self):
        trip = self._trip()
        trip.date_departure = self._at(0)
        second, first = self._loaded(trip), self._loaded(trip)
        self._deliver(second, 90)
        self._deliver(first, 40)
        trip.date_return = self._at(150)
        for minutes, odometer in (
            (0, 1000.0),
            (40, 1012.5),
            (90, 1020.0),
            (150, 1045.0),
        ):
            self._log(minutes, odometer)
        trip.action_capture_gps_legs()
        self.assertAlmostEqual(first.trip_leg_km, 12.5)
        self.assertAlmostEqual(second.trip_leg_km, 7.5)
        self.assertAlmostEqual(trip.trip_return_leg_km, 25.0)
        self.assertAlmostEqual(
            trip.trip_gps_km,
            45.0,
            msg="Legs read from the odometer add up to the whole trip.",
        )

    def test_deliveries_to_one_address_in_a_row_are_one_leg(self):
        trip = self._trip()
        trip.date_departure = self._at(0)
        ranch = self.env["res.partner"].create({"name": "Rancho Norte"})
        first, second, last = self._loaded(trip), self._loaded(trip), self._loaded(trip)
        (first | second).partner_id = ranch
        self._deliver(first, 40)
        self._deliver(second, 45)
        self._deliver(last, 90)
        trip.date_return = self._at(150)
        for minutes, odometer in (
            (0, 1000.0),
            (40, 1012.5),
            (45, 1013.0),
            (90, 1020.0),
            (150, 1045.0),
        ):
            self._log(minutes, odometer)
        trip.action_capture_gps_legs()
        self.assertEqual(
            sorted((first | second).mapped("trip_leg_km")),
            [0.0, 13.0],
            "One stop, one leg: up to when the vehicle left the address.",
        )
        self.assertAlmostEqual(last.trip_leg_km, 7.0)
        self.assertAlmostEqual(trip.trip_return_leg_km, 25.0)
        self.assertAlmostEqual(trip.trip_gps_km, 45.0)

    def test_a_leg_without_odometer_is_measured_between_positions(self):
        trip = self._trip()
        trip.date_departure = self._at(0)
        picking = self._loaded(trip)
        self._deliver(picking, 30)
        self._log(0, latitude=19.26, longitude=-99.60)
        self._log(15, latitude=19.30, longitude=-99.60)
        self._log(30, latitude=19.35, longitude=-99.60)
        trip.action_capture_gps_legs()
        self.assertAlmostEqual(picking.trip_leg_km, 10.0, delta=0.5)

    def test_capturing_needs_a_gps_device(self):
        trip = self._trip()
        trip.date_departure = self._at(0)
        self.asset.gps_device_id = False
        with self.assertRaisesRegex(UserError, "has no GPS device"):
            trip.action_capture_gps_legs()

    def test_a_dispatcher_who_cannot_read_gps_logs_still_gets_the_kilometres(self):
        dispatcher = self.env["res.users"].create(
            {
                "name": "Dispatcher",
                "login": "trip_dispatcher",
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("stock.group_stock_user").id,
                        ]
                    )
                ],
            }
        )
        self.assertFalse(
            self.env["device.data.log.gps"].with_user(dispatcher).has_access("read")
        )
        trip = self._trip()
        trip.date_departure = self._at(0)
        picking = self._loaded(trip)
        self._deliver(picking, 40)
        self._log(0, 1000.0)
        self._log(40, 1012.5)
        trip.with_user(dispatcher).action_capture_gps_legs()
        self.assertAlmostEqual(picking.trip_leg_km, 12.5)

    def test_the_return_leg_reads_the_odometer_the_vehicle_parked_with(self):
        trip = self._trip()
        trip.date_departure = self._at(0)
        picking = self._loaded(trip)
        self._deliver(picking, 40)
        trip.date_return = self._at(190)
        self._log(0, 1000.0)
        self._log(40, 1012.5)
        self._log(100, 1030.0)
        trip.action_capture_gps_legs()
        self.assertAlmostEqual(picking.trip_leg_km, 12.5)
        self.assertAlmostEqual(trip.trip_return_leg_km, 17.5)
        self.assertAlmostEqual(trip.trip_gps_km, 30.0)
