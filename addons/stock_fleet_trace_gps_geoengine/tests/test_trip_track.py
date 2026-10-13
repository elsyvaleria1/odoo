from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time
from lxml import etree

from odoo import Command, fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged

from odoo.addons.device_gps.tests.route_simulator import (
    RouteSimulator,
    make_gps_device,
)
from odoo.addons.geoengine.models.static_map import TileFetcher

WAREHOUSE = (19.2826000, -99.6557000)
CUSTOMER = (19.2900000, -99.6700000)
SVG = "{http://www.w3.org/2000/svg}"


@tagged("post_install", "-at_install")
class TestTripTrack(TransactionCase):
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
                "login": "track_supervisor",
                "group_ids": [
                    Command.set([cls.env.ref("stock.group_stock_manager").id])
                ],
            }
        )
        kind = cls.env.ref("base.kind_vehicle")
        model = cls.env["product.product"].create(
            {"name": "Truck", "type": "consu", "asset_kind_id": kind.id}
        )
        asset = cls.env["resource.resource"].create(
            {"name": "Truck", "kind_id": kind.id, "product_id": model.id}
        )
        cls.vehicle = cls.env["resource.asset.vehicle"].browse(asset.id)
        cls.vehicle.trip_delivery_vehicle = True
        with freeze_time("2026-01-01"):
            cls.device = make_gps_device(cls.env, cls.vehicle, "SIM-TRACK")
        cls.product = cls.env["product.product"].create(
            {"name": "Fertiliser", "is_storable": True, "weight": 25.0}
        )
        stock = cls.warehouse.lot_stock_id
        cls.env["stock.quant"]._update_available_quantity(cls.product, stock, 50)
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Customer One",
                "partner_latitude": CUSTOMER[0],
                "partner_longitude": CUSTOMER[1],
            }
        )
        customers = cls.env.ref("stock.stock_location_customers")
        cls.delivery = cls.env["stock.picking"].create(
            {
                "picking_type_id": cls.out_type.id,
                "partner_id": cls.customer.id,
                "location_id": stock.id,
                "location_dest_id": customers.id,
                "move_ids": [
                    Command.create(
                        {
                            "product_id": cls.product.id,
                            "product_uom_qty": 4,
                            "location_id": stock.id,
                            "location_dest_id": customers.id,
                        }
                    )
                ],
            }
        )
        cls.delivery.action_confirm()
        cls.delivery.action_assign()
        cls.trip = cls.env["stock.picking.batch"].create(
            {
                "picking_type_id": cls.out_type.id,
                "picking_ids": [Command.set(cls.delivery.ids)],
                "vehicle_id": cls.vehicle.id,
                "operator_id": cls.env["hr.employee"].create({"name": "Driver"}).id,
                "supervisor_id": cls.supervisor.id,
                "odometer_departure": 1.0,
                "fuel_departure": 1.0,
            }
        )
        cls.trip.action_trip_load()

    def _sync(self):
        self.env["stock.picking.batch"]._trip_gps_sync_vehicle(self.vehicle)

    def test_the_track_draws_the_road_and_marks_the_stops(self):
        route = RouteSimulator(
            self.env,
            self.device,
            start=fields.Datetime.now() - timedelta(hours=3),
            latitude=WAREHOUSE[0],
            longitude=WAREHOUSE[1],
            odometer_km=28819.0,
            fuel_percent=80.0,
        )
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER)
        route.dwell(6)
        self._sync()
        self.delivery.action_deliver()
        route.drive_to(*WAREHOUSE)
        route.dwell(2)
        self._sync()
        self.assertEqual(self.trip.trip_state, "closed")

        action = self.trip.with_user(self.supervisor).action_trip_view_gps_track()

        self.assertEqual(action["res_model"], "wizard.device.device.view.trail.result")
        trail = self.env["wizard.device.device.view.trail.result"].search(
            action["domain"]
        )
        self.assertEqual(len(trail), 1)
        self.assertTrue(trail.the_trail)
        self.assertGreater(trail.point_count, 10)
        self.assertIn(self.trip.name, trail.name)
        layers = self.env["wizard.device.device.view.trail.result"].get_layers(
            self.env.ref("device_gps_geoengine.view_gps_trail_result_geoengine").id
        )
        self.assertEqual(layers["validation"]["errors"], [])
        stops = self.env["wizard.stock.trip.track.point"].search(
            [("trail_result_id", "=", trail.id)]
        )
        self.assertTrue(stops)
        self.assertTrue(
            stops.get_views([(False, "geoengine")])["views"]["geoengine"]["arch"]
        )
        Result = self.env["wizard.device.device.view.trail.result"]
        self.assertEqual(
            Result.with_user(self.supervisor).search(action["domain"]), trail
        )
        clerk = self.env["res.users"].create(
            {
                "name": "Track Clerk",
                "login": "track_clerk",
                "group_ids": [Command.set([self.env.ref("stock.group_stock_user").id])],
            }
        )
        self.assertFalse(Result.with_user(clerk).search([("id", "=", trail.id)]))
        points = self.env["wizard.stock.trip.track.point"].search(
            [("trail_result_id", "=", trail.id)]
        )
        stop = points.filtered(lambda p: p.kind == "stop")
        self.assertEqual(len(stop), 1)
        self.assertIn(self.delivery.name, stop.name)
        self.assertTrue(stop.the_point)
        self.assertTrue(stop.color)
        self.assertLessEqual({"departure", "return"}, set(points.mapped("kind")))

    def test_a_stock_user_draws_the_track_and_the_map_can_show_it(self):
        clerk = self.env["res.users"].create(
            {
                "name": "Dispatch Clerk",
                "login": "track_dispatch_clerk",
                "group_ids": [Command.set([self.env.ref("stock.group_stock_user").id])],
            }
        )
        self.assertFalse(self.env["device.device"].with_user(clerk).has_access("read"))
        route = RouteSimulator(
            self.env,
            self.device,
            start=fields.Datetime.now() - timedelta(hours=3),
            latitude=WAREHOUSE[0],
            longitude=WAREHOUSE[1],
            odometer_km=28819.0,
            fuel_percent=80.0,
        )
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER)
        route.dwell(6)
        self._sync()

        action = self.trip.with_user(clerk).action_trip_view_gps_track()

        Result = self.env["wizard.device.device.view.trail.result"].with_user(clerk)
        trail = Result.search(action["domain"])
        self.assertEqual(len(trail), 1)
        self.assertNotIn("gps_trail_selection_summary", action["context"])
        trail.read(["name", "the_trail", "device_name", "length_km"])
        points = (
            self.env["wizard.stock.trip.track.point"]
            .with_user(clerk)
            .search_read(
                [("trail_result_id", "in", trail.ids)],
                ["name", "kind", "date", "color", "the_point"],
            )
        )
        self.assertIn("stop", {point["kind"] for point in points})
        keys = [(p["kind"], p["name"], p["the_point"]) for p in points]
        self.assertEqual(len(keys), len(set(keys)))
        layers = Result.get_layers(
            self.env.ref("device_gps_geoengine.view_gps_trail_result_geoengine").id
        )
        self.assertTrue(layers["validation"]["valid"], layers["validation"])
        self.assertIn(
            "wizard.stock.trip.track.point",
            [layer.get("model") for layer in layers["actives"]],
        )

    def test_reading_the_trip_is_not_drawing_its_track(self):
        self.trip.action_depart()
        readers = self.env["res.groups"].create({"name": "Trip readers"})
        self.env["ir.access"].create(
            {
                "name": "Trip readers read the trips",
                "model_id": self.env["ir.model"]._get_id("stock.picking.batch"),
                "group_id": readers.id,
                "kind": "permission",
                "operation": "r",
            }
        )
        reader = self.env["res.users"].create(
            {
                "name": "Trip Reader",
                "login": "track_trip_reader",
                "group_ids": [
                    Command.set([self.env.ref("base.group_user").id, readers.id])
                ],
            }
        )
        trip = self.trip.with_user(reader)
        self.assertTrue(trip.has_access("read"))
        self.assertFalse(trip.has_access("view_gps_track"))
        with self.assertRaises(AccessError):
            trip.action_trip_view_gps_track()

    def test_detaching_a_tracker_preserves_the_trip_history_lookup(self):
        self.trip.action_depart()
        self.vehicle.gps_device_id = False
        self.assertTrue(self.trip.has_trip_gps)
        with self.assertRaisesRegex(UserError, "has no GPS track to draw"):
            self.trip.action_trip_view_gps_track()

    def test_a_trip_without_readings_says_so(self):
        self.trip.action_depart()
        with self.assertRaisesRegex(UserError, "has no GPS track to draw"):
            self.trip.action_trip_view_gps_track()

    def test_a_trip_that_has_not_departed_has_no_track(self):
        with self.assertRaisesRegex(UserError, "has not departed"):
            self.trip.action_trip_view_gps_track()

    def test_track_requires_access_to_its_trip_before_creating_a_trail(self):
        Result = self.env["wizard.device.device.view.trail.result"]
        before = Result.search_count([])
        with self.assertRaises(AccessError):
            self.trip.with_user(
                self.env.ref("base.public_user")
            ).action_trip_view_gps_track()
        self.assertEqual(Result.search_count([]), before)

    def _clerk(self):
        return self.env["res.users"].create(
            {
                "name": "Sheet Clerk",
                "login": "route_sheet_clerk",
                "group_ids": [Command.set([self.env.ref("stock.group_stock_user").id])],
            }
        )

    def _drive(self):
        route = RouteSimulator(
            self.env,
            self.device,
            start=fields.Datetime.now() - timedelta(hours=3),
            latitude=WAREHOUSE[0],
            longitude=WAREHOUSE[1],
            odometer_km=28819.0,
            fuel_percent=80.0,
        )
        route.dwell(2, ignition=True)
        route.drive_to(*CUSTOMER)
        route.dwell(6)
        self._sync()

    def test_the_printed_route_draws_the_road_and_numbers_the_stops(self):
        self._drive()
        with patch.object(TileFetcher, "tile", return_value=None):
            svg = self.trip.with_user(self._clerk())._trip_route_map()
        tree = etree.fromstring(str(svg).encode())
        [road] = tree.iter(f"{SVG}polyline")
        self.assertGreater(len(road.get("points").split()), 1)
        labels = [text.text for text in tree.iter(f"{SVG}text")]
        self.assertEqual(
            labels,
            [str(self.delivery.batch_sequence)],
            "the one stop carries the sequence the sheet prints, nothing else is numbered",
        )
        circles = list(tree.iter(f"{SVG}circle"))
        self.assertGreater(len(circles), 1, "events are marked beside the stop")
        self.assertEqual(
            circles[-1].getnext().text,
            str(self.delivery.batch_sequence),
            "the numbered stop is drawn last, over the events at its place",
        )

    def test_a_trip_not_yet_departed_prints_its_stops_without_a_road(self):
        with patch.object(TileFetcher, "tile", return_value=None):
            svg = self.trip._trip_route_map()
        tree = etree.fromstring(str(svg).encode())
        self.assertEqual(list(tree.iter(f"{SVG}polyline")), [])
        self.assertEqual(
            [text.text for text in tree.iter(f"{SVG}text")],
            [str(self.delivery.batch_sequence)],
        )

    def test_the_trip_sheet_carries_the_route(self):
        self._drive()
        with patch.object(TileFetcher, "tile", return_value=None):
            html = (
                self.env["ir.actions.report"]
                ._render_qweb_html(
                    "stock_picking_batch.report_picking_batch", self.trip.ids
                )[0]
                .decode()
            )
        self.assertIn("o_trip_route_map", html)
        self.assertIn("o_geoengine_static_map", html)
