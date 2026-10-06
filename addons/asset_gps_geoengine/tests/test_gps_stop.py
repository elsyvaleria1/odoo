from datetime import date, datetime, timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo.exceptions import UserError
from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged

# 2026-09-07 in Mexico City is UTC-6: 15:00 UTC is 09:00 local, same day.
DAY = date(2026, 9, 7)
T0 = datetime(2026, 9, 7, 15, 0)
# Inside the client parcel below.
ON_PARCEL = (19.40, -99.10)
# About 1.1 km north of the parcel: no geofence, but a client parcel nearby.
OFF_PARCEL = (19.42, -99.10)
# Far from everything.
ELSEWHERE = (20.50, -101.00)


@tagged("post_install", "-at_install")
class TestGpsStop(common.TransactionCase):
    def setUp(self):
        super().setUp()
        category = self.env.ref("device.device_category_gps")
        self.device, self.silent = self.env["device.device"].create(
            [
                {
                    "name": "Stop Tracker",
                    "identifier": "STOP-001",
                    "comm_protocol": "http",
                    "imei": "TEST-IMEI-STOP-001",
                    "device_category_id": category.id,
                },
                {
                    "name": "Silent Tracker",
                    "identifier": "STOP-002",
                    "comm_protocol": "http",
                    "imei": "TEST-IMEI-STOP-002",
                    "device_category_id": category.id,
                },
            ]
        )
        self._set_created(self.device | self.silent, datetime(2026, 1, 1))
        self.client = self.env["res.partner"].create({"name": "Stop Client"})
        self.parcel = self.env["device.geo.fence"].create(
            {
                "name": "Stop Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": self.client.id,
                "polygon_points": json_dumps(
                    [[19.39, -99.11], [19.41, -99.11], [19.41, -99.09], [19.39, -99.09]]
                ),
            }
        )

    @freeze_time("2026-09-08")
    def test_stops_are_partitioned_by_resource_timezone(self):
        for device, timezone in (
            (self.device, "America/Mexico_City"),
            (self.silent, "Asia/Tokyo"),
        ):
            with freeze_time("2026-09-01"):
                self.env["resource.resource"].create(
                    {"name": device.name, "gps_device_id": device.id, "tz": timezone}
                )
            self._log(device, datetime(2026, 9, 7, 3), ON_PARCEL, 0)
            self._log(device, datetime(2026, 9, 7, 4), ON_PARCEL, 0)
            self._log(device, datetime(2026, 9, 7, 4, 30), ON_PARCEL, 30)
        self.env.flush_all()
        self.env["device.gps.stop"]._refresh(
            date(2026, 9, 6), DAY, devices=self.device | self.silent
        )
        stops = self.env["device.gps.stop"].search(
            [
                ("device_id", "in", (self.device | self.silent).ids),
                ("kind", "=", "stop"),
            ]
        )
        dates = {stop.device_id.id: stop.date for stop in stops}
        self.assertEqual(dates[self.device.id], date(2026, 9, 6))
        self.assertEqual(dates[self.silent.id], DAY)

    @freeze_time("2026-09-08")
    def test_timezone_change_rebuilds_settled_stop_dates(self):
        with freeze_time("2026-09-01"):
            resource = self.env["resource.resource"].create(
                {
                    "name": "Moving timezone",
                    "gps_device_id": self.device.id,
                    "tz": "America/Mexico_City",
                }
            )
        self._log(self.device, datetime(2026, 9, 7, 3), ON_PARCEL, 0)
        self._log(self.device, datetime(2026, 9, 7, 4), ON_PARCEL, 0)
        self._log(self.device, datetime(2026, 9, 7, 4, 30), ON_PARCEL, 30)
        report = self.env["device.gps.stop"]
        self.env.flush_all()
        report._refresh(date(2026, 9, 6), DAY, devices=self.device)
        resource.tz = "Asia/Tokyo"
        with freeze_time("2026-10-02"), patch.object(type(report), "_name_places"):
            report._cron_refresh()
        stop = report.search(
            [("device_id", "=", self.device.id), ("kind", "=", "stop")]
        )
        self.assertEqual(stop.date, DAY)

    def _set_created(self, devices, when):
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE device_device SET create_date = %s WHERE id = ANY(%s)",
            (when, devices.ids),
        )
        devices.invalidate_recordset(["create_date"])

    def _log(self, device, when, point, speed):
        self.env["device.data.log.gps"].create(
            {
                "device_id": device.id,
                "timestamp": when,
                "latitude": point[0],
                "longitude": point[1],
                "speed": speed,
            }
        )

    def _still(self, start, minutes, point, every=5):
        for i in range(0, minutes + 1, every):
            self._log(self.device, start + timedelta(minutes=i), point, 0)

    def _stops(self, devices=None):
        devices = devices or self.device
        self.env.flush_all()
        self.env["device.gps.stop"]._refresh(DAY, DAY, devices=devices)
        return self.env["device.gps.stop"].search(
            [("device_id", "in", devices.ids)], order="arrival"
        )

    def test_stop_on_a_client_parcel_ends_at_the_first_moving_position(self):
        self._log(self.device, T0, OFF_PARCEL, 40)
        self._still(T0 + timedelta(minutes=5), 20, ON_PARCEL)
        self._log(self.device, T0 + timedelta(minutes=32), ON_PARCEL, 30)

        stop = self._stops()
        self.assertEqual(len(stop), 1)
        self.assertEqual(stop.kind, "stop")
        self.assertEqual(stop.date, DAY)
        self.assertEqual(stop.arrival, T0 + timedelta(minutes=5))
        self.assertEqual(stop.departure, T0 + timedelta(minutes=32))
        self.assertAlmostEqual(stop.duration_hours, 27 / 60, places=4)
        self.assertFalse(stop.ongoing)
        self.assertEqual(stop.geofence_id, self.parcel)
        self.assertEqual(stop.partner_id, self.client)
        self.assertIn("Stop Parcel (Stop Client)", stop.place)

    def test_stop_outside_geofences_names_the_nearest_client_parcel(self):
        self._still(T0, 15, OFF_PARCEL)
        self._log(self.device, T0 + timedelta(minutes=20), OFF_PARCEL, 50)

        stop = self._stops()
        self.assertFalse(stop.geofence_id)
        self.assertFalse(stop.partner_id)
        self.assertEqual(stop.nearby_geofence_id, self.parcel)
        self.assertLess(stop.nearby_distance_m, 1200)
        self.assertIn("from Stop Parcel (Stop Client)", stop.place)
        self.assertIn("19.420000,-99.100000", stop.map_url)

    def test_map_colour_marks_long_stops_outside_geofences(self):
        # 10 min on the parcel, 15 min off it, 40 min far from everything.
        self._still(T0, 10, ON_PARCEL)
        self._log(self.device, T0 + timedelta(minutes=10), ON_PARCEL, 30)
        self._still(T0 + timedelta(hours=1), 15, OFF_PARCEL)
        self._log(self.device, T0 + timedelta(hours=1, minutes=15), OFF_PARCEL, 30)
        self._still(T0 + timedelta(hours=2), 40, ELSEWHERE)
        self._log(self.device, T0 + timedelta(hours=2, minutes=40), ELSEWHERE, 30)

        on_parcel, short_off, long_off = self._stops()
        self.assertEqual(on_parcel.map_color, "#198754")
        self.assertEqual(short_off.map_color, "#0d6efd")
        self.assertEqual(long_off.map_color, "#fd7e14")
        self.assertTrue(long_off.the_point)
        self.env.cr.execute(
            "SELECT ST_X(the_point), ST_Y(the_point), ST_SRID(the_point)"
            "  FROM device_gps_stop WHERE id = %s",
            (long_off.id,),
        )
        lon, lat, srid = self.env.cr.fetchone()
        self.assertAlmostEqual(lat, ELSEWHERE[0], places=5)
        self.assertAlmostEqual(lon, ELSEWHERE[1], places=5)
        self.assertEqual(srid, 4326)
        self.assertEqual(
            self.env["device.gps.stop"].search(
                [
                    ("device_id", "=", self.device.id),
                    ("kind", "=", "stop"),
                    ("to_mark", "=", True),
                ]
            ),
            long_off,
        )

    def _fake_nominatim(self, answers):
        calls = []

        def reverse(model, latitude, longitude):
            calls.append((latitude, longitude))
            return answers[len(calls) - 1]

        return calls, patch.object(
            type(self.env["geocoder"]), "_call_openstreetmap_reverse", reverse
        )

    def test_a_stop_outside_geofences_says_what_the_place_is(self):
        self._still(T0, 30, ELSEWHERE)
        self._log(self.device, T0 + timedelta(minutes=35), ELSEWHERE, 40)
        fonda = {
            "class": "amenity",
            "type": "restaurant",
            "name": "Fonda Lupita",
            "address": {"road": "Calle Hidalgo", "village": "Tenango"},
        }
        calls, fake = self._fake_nominatim([fonda])
        stop = self._stops()
        with fake, patch("time.sleep"):
            self.env["device.gps.stop"]._name_places(DAY, self.device)
        self.assertEqual(len(calls), 1)
        self.assertEqual(stop.place_id.name, "Fonda Lupita")
        self.assertEqual(
            stop.place_id.label, "Fonda Lupita (Restaurant) · Calle Hidalgo, Tenango"
        )
        self.assertIn("Fonda Lupita (Restaurant)", stop.place)

        # The ten-minute rewrite keeps the name without asking again.
        calls, fake = self._fake_nominatim([])
        with fake:
            stop = self._stops()
            self.env["device.gps.stop"]._name_places(DAY, self.device)
        self.assertFalse(calls)
        self.assertEqual(stop.place_id.name, "Fonda Lupita")

    def test_a_place_on_a_road_is_its_address(self):
        places = self.env["device.gps.place"]
        road, shop, area = places.create(
            [
                {
                    "name": "Calle Morelos",
                    "osm_category": "highway",
                    "osm_type": "residential",
                    "address": "Calle Morelos, Tenango",
                },
                {
                    "osm_category": "shop",
                    "osm_type": "florist",
                    "address": "Calzada Independencia, Guadalajara",
                },
                {
                    "name": "Rancho El Sauz",
                    "osm_category": "place",
                    "osm_type": "farm",
                    "address": "Tenango",
                },
            ]
        )
        self.assertEqual(road.label, "Calle Morelos, Tenango")
        self.assertEqual(shop.label, "Florist · Calzada Independencia, Guadalajara")
        self.assertEqual(area.label, "Rancho El Sauz · Tenango")

    def test_places_on_a_geofence_are_not_looked_up(self):
        self._still(T0, 30, ON_PARCEL)
        calls, fake = self._fake_nominatim([])
        self._stops()
        with fake:
            self.env["device.gps.stop"]._name_places(DAY, self.device)
        self.assertFalse(calls)

    def test_a_failing_nominatim_does_not_break_the_refresh(self):
        self._still(T0, 30, ELSEWHERE)

        def down(model, latitude, longitude):
            raise UserError("unreachable")

        stop = self._stops()
        with patch.object(
            type(self.env["geocoder"]), "_call_openstreetmap_reverse", down
        ):
            self.env["device.gps.stop"]._name_places(DAY, self.device)
        self.assertFalse(stop.place_id)

    def _unmarked_parcel(self, **vals):
        return self.env["device.geo.fence"].create(
            {
                "name": "Unmarked Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "polygon_points": json_dumps(
                    [
                        [20.49, -101.01],
                        [20.51, -101.01],
                        [20.51, -100.99],
                        [20.49, -100.99],
                    ]
                ),
                **vals,
            }
        )

    def test_a_geofence_without_client_stays_to_mark_after_the_vehicle_leaves(self):
        fences = self.env["device.geo.fence"]
        unmarked = self._unmarked_parcel()
        self._still(T0, 30, ELSEWHERE)
        self._log(self.device, T0 + timedelta(minutes=40), OFF_PARCEL, 50)

        stop = self._stops()[0]
        self.assertEqual(stop.geofence_id, unmarked)
        self.assertFalse(stop.ongoing)
        self.assertTrue(stop.to_mark)
        self.assertEqual(stop.map_color, "#fd7e14")
        self.assertEqual(fences.search([("to_mark", "=", True)]), unmarked)
        self.assertTrue(unmarked.to_mark)
        self.assertNotIn(self.parcel, fences.search([("to_mark", "=", True)]))

        # Someone marks it: it gets a client, and both clear at once.
        unmarked.partner_id = self.client
        stop.invalidate_recordset()
        unmarked.invalidate_recordset()
        self.assertFalse(stop.to_mark)
        self.assertFalse(unmarked.to_mark)
        self.assertFalse(fences.search([("to_mark", "=", True)]))

    def test_a_place_without_geofence_is_to_mark_until_one_is_drawn(self):
        self._still(T0, 30, ELSEWHERE)
        self._log(self.device, T0 + timedelta(minutes=40), OFF_PARCEL, 50)
        stop = self._stops()[0]
        self.assertFalse(stop.geofence_id)
        self.assertTrue(stop.to_mark)

        self._unmarked_parcel(partner_id=self.client.id)
        stop.invalidate_recordset()
        self.assertFalse(stop.to_mark)

    def test_internal_geofences_and_short_stops_are_not_to_mark(self):
        self._unmarked_parcel(usage="internal")
        self._still(T0, 30, ELSEWHERE)
        self._log(self.device, T0 + timedelta(minutes=40), OFF_PARCEL, 50)
        self._still(T0 + timedelta(hours=1), 10, OFF_PARCEL)
        self._log(self.device, T0 + timedelta(hours=1, minutes=15), OFF_PARCEL, 50)
        internal, short = self._stops()
        self.assertFalse(internal.to_mark)
        self.assertFalse(short.to_mark)
        self.assertEqual(short.map_color, "#0d6efd")
        self.assertFalse(self.env["device.geo.fence"].search([("to_mark", "=", True)]))

    def test_a_long_stop_at_a_client_is_not_to_mark(self):
        self._still(T0, 30, ON_PARCEL)
        stop = self._stops()
        self.assertFalse(stop.to_mark)
        self.assertEqual(stop.map_color, "#198754")

    def test_the_map_says_where_a_parked_vehicle_is_and_for_how_long(self):
        now = T0 + timedelta(hours=1, minutes=10)
        self._log(self.device, T0, OFF_PARCEL, 40)
        self._still(T0 + timedelta(minutes=5), 60, ON_PARCEL)
        with patch("odoo.fields.Datetime.now", return_value=now):
            self._stops()
            self.device.invalidate_recordset()
            self.assertFalse(self.device.gps_movement_state)
            self.assertIn("Stop Parcel (Stop Client)", self.device.stay_place)
            self.assertEqual(self.device.stay_since, T0 + timedelta(minutes=5))
            self.assertEqual(self.device.stay_elapsed, "1 h 05 min")

    def test_a_moving_vehicle_is_not_tied_to_the_parcel_it_left(self):
        now = T0 + timedelta(hours=1)
        self._still(T0, 30, ON_PARCEL)
        self._log(self.device, T0 + timedelta(minutes=40), OFF_PARCEL, 60)
        last = self.env["device.data.log.gps"].search(
            [("device_id", "=", self.device.id)], order="timestamp desc", limit=1
        )
        last.movement = True
        self.device.log_gps_last_id = last
        with patch("odoo.fields.Datetime.now", return_value=now):
            self._stops()
            self.device.invalidate_recordset()
            self.assertTrue(self.device.gps_movement_state)
            self.assertFalse(self.device.stay_place)
            self.assertEqual(self.device.stay_since, T0 + timedelta(minutes=40))
            self.assertEqual(self.device.stay_elapsed, "20 min")

    def test_a_short_halt_is_not_a_stop(self):
        self._still(T0, 3, OFF_PARCEL, every=1)
        self._log(self.device, T0 + timedelta(minutes=4), OFF_PARCEL, 40)
        self.assertFalse(self._stops())

    def test_a_sleeping_tracker_stop_lasts_until_it_moves_again(self):
        self._log(self.device, T0, ELSEWHERE, 0)
        self._log(self.device, T0 + timedelta(minutes=40), ELSEWHERE, 35)

        stop = self._stops()
        self.assertEqual(stop.positions, 1)
        self.assertAlmostEqual(stop.duration_hours, 40 / 60, places=4)

    def test_waking_up_somewhere_else_is_two_stops(self):
        self._still(T0, 10, ON_PARCEL)
        self._still(T0 + timedelta(hours=2), 10, ELSEWHERE)
        self._log(self.device, T0 + timedelta(hours=3), ELSEWHERE, 60)

        first, second = self._stops()
        self.assertEqual(first.departure, second.arrival)
        self.assertEqual(first.partner_id, self.client)
        self.assertFalse(second.geofence_id)
        self.assertEqual(second.departure, T0 + timedelta(hours=3))

    def test_a_stop_without_departure_is_ongoing(self):
        self._log(self.device, T0, OFF_PARCEL, 40)
        self._still(T0 + timedelta(minutes=5), 10, ON_PARCEL)

        stop = self._stops()
        self.assertTrue(stop.ongoing)
        self.assertFalse(stop.departure)

    def test_a_device_without_positions_is_listed(self):
        before = T0 - timedelta(days=3)
        self._log(self.silent, before, ELSEWHERE, 0)

        rows = self._stops(self.silent)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows.kind, "no_signal")
        self.assertEqual(rows.date, DAY)
        self.assertEqual(rows.last_seen, before)

    def test_no_row_before_the_device_existed(self):
        self._set_created(self.silent, datetime(2026, 9, 8, 12, 0))
        self.assertFalse(self._stops(self.silent))

    def test_refresh_is_idempotent(self):
        self._still(T0, 15, ON_PARCEL)
        self._log(self.device, T0 + timedelta(minutes=20), ON_PARCEL, 40)
        devices = self.device | self.silent

        def shape(rows):
            return sorted(
                (s.device_id.id, s.kind, str(s.arrival), str(s.departure)) for s in rows
            )

        first = shape(self._stops(devices))
        self.assertEqual(len(first), 2)
        self.assertEqual(shape(self._stops(devices)), first)

    def test_pdf_groups_by_vehicle_and_day(self):
        self._still(T0, 15, ON_PARCEL)
        self._log(self.device, T0 + timedelta(minutes=20), ON_PARCEL, 40)
        rows = self._stops(self.device | self.silent)
        html, _ = self.env["ir.actions.report"]._render_qweb_html(
            "asset_gps_geoengine.report_device_gps_stop_action", rows.ids
        )
        html = html.decode()
        self.assertIn("Stop Tracker", html)
        self.assertIn("Silent Tracker", html)
        self.assertIn("Stop Parcel (Stop Client)", html)
