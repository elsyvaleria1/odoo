from datetime import timedelta

from freezegun import freeze_time

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged

from .gps_simulator import RouteSimulator, make_gps_device

WAREHOUSE = (19.2826000, -99.6557000)
CUSTOMER_1 = (19.2900000, -99.6700000)
CUSTOMER_2 = (19.3000000, -99.6800000)
ROADSIDE = (19.2950000, -99.6600000)


@tagged("post_install", "-at_install")
class TestTripGps(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.write(
            {
                "trip_origin_latitude": WAREHOUSE[0],
                "trip_origin_longitude": WAREHOUSE[1],
                "trip_geofence_radius": 150,
            }
        )
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.customer_location = cls.env.ref("stock.stock_location_customers")
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
                "login": "gps_supervisor",
                "group_ids": [
                    Command.set([cls.env.ref("stock.group_stock_manager").id])
                ],
            }
        )
        cls.driver = cls.env["hr.employee"].create({"name": "Driver"})
        kind = cls.env.ref("base.kind_vehicle")
        model = cls.env["product.product"].create(
            {"name": "Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        cls.vehicle = cls.env["resource.resource"].create(
            {"name": "Truck", "kind_id": kind.id, "product_id": model.id}
        )
        cls.vehicle = cls.env["resource.asset.vehicle"].browse(cls.vehicle.id)
        cls.vehicle.trip_delivery_vehicle = True
        with freeze_time("2026-01-01"):
            cls.device = make_gps_device(cls.env, cls.vehicle, "SIM-0001")
        cls.product = cls.env["product.product"].create(
            {"name": "Fertiliser", "is_storable": True, "weight": 25.0}
        )
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.stock_location, 500
        )
        cls.customer_1 = cls.env["res.partner"].create(
            {
                "name": "Customer One",
                "partner_latitude": CUSTOMER_1[0],
                "partner_longitude": CUSTOMER_1[1],
            }
        )
        cls.customer_2 = cls.env["res.partner"].create(
            {
                "name": "Customer Two",
                "partner_latitude": CUSTOMER_2[0],
                "partner_longitude": CUSTOMER_2[1],
            }
        )

    def _delivery(self, partner, quantity=4):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.out_type.id,
                "partner_id": partner.id,
                "location_id": self.stock_location.id,
                "location_dest_id": self.customer_location.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_uom_qty": quantity,
                            "location_id": self.stock_location.id,
                            "location_dest_id": self.customer_location.id,
                        }
                    )
                ],
            }
        )
        picking.action_confirm()
        picking.action_assign()
        return picking

    def _trip(self, pickings, load=True):
        trip = self.env["stock.picking.batch"].create(
            {
                "picking_type_id": self.out_type.id,
                "picking_ids": [Command.set(pickings.ids)],
                "vehicle_id": self.vehicle.id,
                "operator_id": self.driver.id,
                "supervisor_id": self.supervisor.id,
                "odometer_departure": 1.0,
                "fuel_departure": 1.0,
            }
        )
        if load:
            trip.action_trip_load()
        return trip

    def _route(self):
        return RouteSimulator(
            self.env,
            self.device,
            start=fields.Datetime.now() - timedelta(hours=3),
            latitude=WAREHOUSE[0],
            longitude=WAREHOUSE[1],
            odometer_km=28819.0,
            fuel_percent=80.0,
        )

    def _sync(self):
        self.env["stock.picking.batch"]._trip_gps_sync_vehicle(self.vehicle)

    def _alerts(self, alert_type):
        return self.env["stock.trip.alert"].search(
            [("vehicle_id", "=", self.vehicle.id), ("alert_type", "=", alert_type)]
        )

    def test_the_geofence_departs_verifies_the_stop_and_returns(self):
        delivery = self._delivery(self.customer_1)
        trip = self._trip(delivery)
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        route.dwell(6)
        self._sync()

        self.assertEqual(trip.trip_state, "in_transit")
        exit_log = route.logs.filtered(
            lambda log: (
                not self.warehouse._trip_geofence_contains(log.latitude, log.longitude)
            )
        )[:1]
        self.assertEqual(trip.date_departure, exit_log.timestamp)
        self.assertAlmostEqual(trip.odometer_departure, exit_log.real_odometer, 1)
        self.assertAlmostEqual(trip.fuel_departure, exit_log.fuel_level, 0)
        departure = trip.trip_checkpoint_ids.filtered(
            lambda c: c.event_type == "departure"
        )
        self.assertEqual(departure.method, "gps")
        self.assertTrue(delivery.trip_gps_verified)
        self.assertTrue(delivery.trip_arrival_date)

        delivery.action_deliver()
        route.drive_to(*WAREHOUSE)
        route.dwell(2)
        self._sync()
        self.assertEqual(trip.trip_state, "closed")
        self.assertTrue(trip.trip_gps_entry_date)
        self.assertGreater(trip.odometer_return, trip.odometer_departure)
        self.assertLess(trip.fuel_return, trip.fuel_departure)
        self.assertEqual(trip.balance_state, "balanced")
        self.assertFalse(self._alerts("outcome_without_visit"))

    def test_only_an_origin_set_on_the_warehouse_draws_a_geofence(self):
        other = self.env["stock.warehouse"].create(
            {"name": "Geocoded only", "code": "GEO"}
        )
        other.partner_id.write(
            {"partner_latitude": WAREHOUSE[0], "partner_longitude": WAREHOUSE[1]}
        )
        self.assertEqual(other._trip_origin(), WAREHOUSE)
        self.assertFalse(other.has_trip_geofence)
        self.assertFalse(other._trip_geofence_contains(*WAREHOUSE))
        self.assertTrue(self.warehouse.has_trip_geofence)

    def test_a_delivery_vehicle_leaving_without_a_trip_raises_an_alert(self):
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        self._sync()
        self.assertEqual(len(self._alerts("departure_without_trip")), 1)
        self._sync()
        self.assertEqual(len(self._alerts("departure_without_trip")), 1)

    def test_a_trip_that_was_not_loaded_does_not_depart_on_its_own(self):
        trip = self._trip(self._delivery(self.customer_1), load=False)
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        self._sync()
        self.assertEqual(trip.trip_state, "planned")
        self.assertEqual(self._alerts("departure_not_loaded").batch_id, trip)

    def test_the_loaded_trip_departs_although_another_is_still_planned(self):
        trip = self._trip(self._delivery(self.customer_1))
        planned = self._trip(self._delivery(self.customer_2), load=False)
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        self._sync()
        self.assertEqual(trip.trip_state, "in_transit")
        self.assertEqual(planned.trip_state, "planned")
        self.assertFalse(self._alerts("departure_not_loaded"))

    def test_an_outcome_the_track_never_visited_is_flagged(self):
        first = self._delivery(self.customer_1)
        second = self._delivery(self.customer_2)
        trip = self._trip(first | second)
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        route.dwell(5)
        self._sync()
        first.action_deliver()
        second.action_deliver()
        route.drive_to(*WAREHOUSE)
        route.dwell(2)
        self._sync()

        self.assertEqual(trip.trip_state, "closed")
        self.assertTrue(first.trip_gps_verified)
        self.assertFalse(second.trip_gps_verified)
        self.assertEqual(self._alerts("outcome_without_visit").picking_id, second)

    def test_the_track_reports_stops_harsh_driving_and_fuel(self):
        delivery = self._delivery(self.customer_1)
        trip = self._trip(delivery)
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*ROADSIDE, harsh_at=0.9)
        route.dwell(15)
        route.refuel(30.0)
        route.drive_to(*CUSTOMER_1)
        route.dwell(5)
        self._sync()

        stop = self._alerts("unplanned_stop")
        self.assertEqual(len(stop), 1)
        self.assertGreaterEqual(stop.duration_minutes, 14)
        self.assertEqual(trip.trip_harsh_event_count, 1)
        self.assertTrue(self._alerts("harsh_driving"))
        fuel = trip.trip_checkpoint_ids.filtered(lambda c: c.event_type == "fuel")
        self.assertEqual(fuel.method, "gps")

        harsh_time = self._alerts("harsh_driving").date
        incident = self.env["stock.trip.incident"].create(
            {
                "batch_id": trip.id,
                "incident_type": "spill",
                "description": "A sack fell when braking",
                "date": harsh_time + timedelta(minutes=2),
            }
        )
        self.assertIn("Harsh driving", incident.gps_note)
        self.assertTrue(incident.latitude)

    def test_a_reading_the_trip_refuses_raises_an_alert_and_reading_goes_on(self):
        delivery = self._delivery(self.customer_1)
        trip = self._trip(delivery, load=False)
        trip.write({"odometer_departure": 99999.0, "fuel_departure": 70.0})
        trip.action_depart()
        delivery.action_deliver()
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        route.dwell(5)
        route.drive_to(*WAREHOUSE)
        route.dwell(2)
        self._sync()

        self.assertEqual(self._alerts("reading_conflict").batch_id, trip)
        self.assertTrue(trip.trip_gps_entry_date)
        self.assertFalse(trip.odometer_return)
        self.assertEqual(self.vehicle.trip_gps_cursor, route.logs[-1].timestamp)

    def test_the_first_reading_inside_the_warehouse_is_not_an_arrival(self):
        delivery = self._delivery(self.customer_1)
        trip = self._trip(delivery, load=False)
        trip.write({"odometer_departure": 28819.0, "fuel_departure": 80.0})
        trip.action_depart()
        route = self._route()
        route.dwell(3, ignition=True)
        self._sync()
        self.assertFalse(trip.trip_gps_entry_date)
        self.assertFalse(trip.odometer_return)
        self.assertFalse(self._alerts("returned_pending"))
        self.assertEqual(self.vehicle.trip_gps_inside_warehouse_id, self.warehouse)

    def _inside(self, log):
        return self.warehouse._trip_geofence_contains(log.latitude, log.longitude)

    def test_a_late_read_dates_the_return_and_its_leg_with_the_track(self):
        delivered = self._delivery(self.customer_1)
        absent = self._delivery(self.customer_2)
        trip = self._trip(delivered | absent)
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        route.dwell(5)
        route.drive_to(*CUSTOMER_2)
        route.dwell(5)
        self._sync()
        delivered.action_deliver()
        absent._register_delivery_failure("Customer absent")
        at_second = route.logs[-1]
        route.drive_to(*WAREHOUSE)
        route.dwell(2)
        entry = route.logs.filtered(
            lambda log: log.timestamp > at_second.timestamp and self._inside(log)
        )[:1]
        route.drive_to(*ROADSIDE)
        route.drive_to(*WAREHOUSE)
        route.dwell(2)
        self._sync()

        self.assertEqual(trip.trip_state, "returned")
        self.assertEqual(trip.date_return, entry.timestamp)
        self.assertAlmostEqual(
            trip.trip_return_leg_km,
            entry.real_odometer - at_second.real_odometer,
            1,
            "The return leg ends where the track came back, not at the read.",
        )
        self.assertGreater(absent.trip_leg_km, 0.0, "A stop not delivered is a leg.")
        self.assertAlmostEqual(
            delivered.trip_leg_km + absent.trip_leg_km + trip.trip_return_leg_km,
            trip.trip_gps_km,
            1,
        )
        self.assertAlmostEqual(
            trip.trip_gps_km, entry.real_odometer - trip.odometer_departure, 1
        )

    def test_two_deliveries_at_one_address_are_one_leg(self):
        first = self._delivery(self.customer_1)
        second = self._delivery(self.customer_1)
        other = self._delivery(self.customer_2)
        trip = self._trip(first | second | other)
        route = self._route()
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER_1)
        route.dwell(5)
        left_first = route.logs[-1]
        route.drive_to(*CUSTOMER_2)
        route.dwell(5)
        self._sync()
        for delivery in first | second | other:
            delivery.action_deliver()
        route.drive_to(*WAREHOUSE)
        route.dwell(2)
        self._sync()

        self.assertEqual(trip.trip_state, "closed")
        legs = sorted((first | second).mapped("trip_leg_km"))
        self.assertEqual(legs[0], 0.0)
        self.assertAlmostEqual(
            legs[1], left_first.real_odometer - trip.odometer_departure, 1
        )
        self.assertGreater(other.trip_leg_km, 0.0)
