from datetime import timedelta

from freezegun import freeze_time

from odoo import fields
from odoo.tests import tagged

from odoo.addons.device_gps.tests.route_simulator import RouteSimulator, make_gps_device
from odoo.addons.stock_fleet_exit.tests.common import FleetExitCommon

WAREHOUSE = (19.2371000, -99.5943300)
DEALERSHIP = (19.2500000, -99.6100000)


@tagged("post_install", "-at_install")
class TestRouteGps(FleetExitCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse.write(
            {
                "trip_origin_latitude": WAREHOUSE[0],
                "trip_origin_longitude": WAREHOUSE[1],
                "trip_geofence_radius": 150,
            }
        )
        with freeze_time("2026-01-01"):
            cls.device = make_gps_device(cls.env, cls.vehicle, "SIM-ROUTE-1")
        cls.notices = []

    def setUp(self):
        super().setUp()
        self.notices.clear()
        self.patch(
            type(self.Batch),
            "_notify_authorisers",
            lambda batches, render, company: self.notices.append(render(batches)) or 1,
        )

    def _route_sim(self, hours_ago=3):
        return RouteSimulator(
            self.env,
            self.device,
            start=fields.Datetime.now() - timedelta(hours=hours_ago),
            latitude=WAREHOUSE[0],
            longitude=WAREHOUSE[1],
            odometer_km=1000.0,
            fuel_percent=80.0,
        )

    def _drive_out_and_back(self, back=True, hours_ago=3):
        route = self._route_sim(hours_ago)
        route.dwell(2, ignition=True)
        route.drive_to(*DEALERSHIP)
        route.dwell(10, ignition=False)
        if back:
            route.drive_to(*WAREHOUSE)
            route.dwell(2, ignition=False)
        return route

    def _sync(self):
        self.Batch._trip_gps_sync_vehicle(self.vehicle)

    def _alerts(self):
        return self.env["stock.trip.alert"].search(
            [
                ("vehicle_id", "=", self.vehicle.id),
                ("alert_type", "=", "departure_without_route"),
            ]
        )

    def test_an_authorised_route_is_stamped_and_closed_by_the_gps(self):
        route = self._ask()
        self._authorise(route)

        self._drive_out_and_back()
        self._sync()

        self.assertTrue(route.trip_gps_exit_date)
        self.assertTrue(route.trip_gps_entry_date)
        self.assertEqual(route.state, "done")
        self.assertGreater(route.odometer_return, route.odometer_departure)
        self.assertEqual(self.vehicle.operator_employee_id, self.holder)
        self.assertFalse(self._alerts())
        self.assertFalse(self.notices)

    def test_leaving_without_a_route_alerts_the_authorisers_once(self):
        self._drive_out_and_back()
        self._sync()
        self._sync()

        self.assertEqual(len(self._alerts()), 1)
        self.assertEqual(len(self.notices), 1)
        self.assertIn("without an authorised route", self.notices[0])
        self.assertIn("maps.google.com", self.notices[0])

    def test_leaving_before_the_authorisation_names_the_waiting_route(self):
        route = self._ask()

        self._drive_out_and_back()
        self._sync()

        self.assertEqual(self._alerts().note, route.name)
        self.assertIn(route.name, self.notices[0])

    def test_a_warehouse_without_exit_log_raises_nothing(self):
        self.warehouse.fleet_exit_log = False

        self._drive_out_and_back()
        self._sync()

        self.assertFalse(self._alerts())
        self.assertFalse(self.notices)

    def test_the_gps_suggests_the_odometer_and_the_place_it_stays(self):
        self.env["device.geo.fence"].create(
            {
                "name": "Agencia Toyota Metepec",
                "geofence_type": "circle",
                "center_latitude": DEALERSHIP[0],
                "center_longitude": DEALERSHIP[1],
                "radius": 200,
            }
        )
        self._drive_out_and_back(back=False, hours_ago=0.5)

        Batch = self.Batch.with_user(self.driver_user)
        vehicle = self.vehicle.with_user(self.driver_user)
        odometer = Batch._get_exit_gps_odometer(vehicle)
        place = Batch._get_exit_gps_place(vehicle)

        self.assertGreater(odometer, 1000.0)
        self.assertEqual(place, "Agencia Toyota Metepec")
