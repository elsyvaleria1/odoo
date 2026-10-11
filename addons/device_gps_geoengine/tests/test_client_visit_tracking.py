from datetime import UTC, datetime, time, timedelta

from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestClientVisitTracking(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        super().setUp()
        self.config = self.env["device.profile"].create({"name": "Visit Test Config"})
        self.device = self.env["device.device"].create(
            {
                "name": "Visit Tracker",
                "identifier": "VISIT-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "imei": "TEST-IMEI-VISIT-001",
                "device_category_id": self.env.ref("device.device_category_gps").id,
            }
        )
        self.client = self._make_parcel("Visited", 19.40, -99.10)

    def _make_parcel(self, name, latitude, longitude):
        partner = self.env["res.partner"].create({"name": f"{name} Client"})
        self.env["device.geo.fence"].create(
            {
                "name": f"{name} Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": partner.id,
                "polygon_points": json_dumps(
                    [
                        [latitude - 0.01, longitude - 0.01],
                        [latitude + 0.01, longitude - 0.01],
                        [latitude + 0.01, longitude + 0.01],
                        [latitude - 0.01, longitude + 0.01],
                    ]
                ),
            }
        )
        return partner

    def _visits(self):
        return self.env["device.client.visit"].search(
            [("device_id", "=", self.device.id)], order="arrival, id"
        )

    def _place(self, latitude, longitude, timestamp=None):
        vals = {
            "device_id": self.device.id,
            "latitude": latitude,
            "longitude": longitude,
        }
        if timestamp:
            vals["timestamp"] = timestamp
        log = self.env["device.data.log.gps"].create(vals)
        self.device.sudo().log_gps_last_id = log.id
        self.env.flush_all()

    def test_arrival_recorded_on_entering(self):
        self._place(19.40, -99.10)

        self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(self.device.client_visit_partner_id, self.client)
        self.assertTrue(self.device.client_visit_arrival)
        self.assertFalse(self.device.client_visit_departure)

    def test_no_change_while_still_on_the_same_parcel(self):
        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()
        first_arrival = self.device.client_visit_arrival

        self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(
            self.device.client_visit_arrival,
            first_arrival,
            "re-detecting the same visit must not reset its arrival time",
        )
        self.assertEqual(
            len(self._visits()), 1, "nor open a second row for the same stay"
        )

    def test_departure_recorded_on_leaving(self):
        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()

        self._place(19.60, -99.60)
        self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(
            self.device.client_visit_partner_id,
            self.client,
            "the just-ended visit's client should stay visible",
        )
        self.assertTrue(self.device.client_visit_departure)

    def test_departure_not_rerecorded(self):
        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()
        self._place(19.60, -99.60)
        self.env["device.device"]._cron_track_client_visits()
        first_departure = self.device.client_visit_departure

        self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(
            self.device.client_visit_departure,
            first_departure,
            "leaving is a one-time transition, not re-stamped every run",
        )

    def test_new_visit_overwrites_the_old_one(self):
        other_client = self._make_parcel("Other", 19.50, -99.20)
        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()

        self._place(19.50, -99.20)
        self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(self.device.client_visit_partner_id, other_client)
        self.assertFalse(
            self.device.client_visit_departure,
            "the new visit is ongoing; it must not carry the old one's departure",
        )

    def test_leaving_closes_the_visit_row_too(self):
        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()

        self._place(19.60, -99.60)
        self.env["device.device"]._cron_track_client_visits()

        visit = self._visits()
        self.assertEqual(len(visit), 1)
        self.assertEqual(visit.departure, self.device.client_visit_departure)

    def test_moving_between_parcels_closes_the_first_visit(self):
        other_client = self._make_parcel("Other", 19.50, -99.20)
        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()

        self._place(19.50, -99.20)
        self.env["device.device"]._cron_track_client_visits()

        first, second = self._visits()
        self.assertEqual(first.partner_id, self.client)
        self.assertTrue(
            first.departure,
            "driving straight from one parcel to the next left the first "
            "visit open forever: duration_hours is now minus arrival, so it "
            "grows without bound and every total grouped by client, operator "
            "or vehicle is wrong",
        )
        self.assertEqual(second.partner_id, other_client)
        self.assertFalse(second.departure)

    def test_returning_to_the_same_parcel_opens_a_second_visit(self):
        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()
        self._place(19.60, -99.60)
        self.env["device.device"]._cron_track_client_visits()

        self._place(19.40, -99.10)
        self.env["device.device"]._cron_track_client_visits()

        first, second = self._visits()
        self.assertTrue(first.departure)
        self.assertFalse(
            second.departure,
            "coming back is a second visit, not a resumed one",
        )
        self.assertFalse(
            self.device.client_visit_departure,
            "the device is on the parcel again, so the map must not still "
            "show it as departed",
        )

    def test_distance_is_zero_inside_and_geodesic_beside(self):
        self._place(19.40, -99.10)
        self.device.invalidate_recordset()
        self.assertEqual(self.device.current_client_partner_id, self.client)
        self.assertEqual(self.device.current_client_distance_m, 0)

        self._place(19.4103, -99.10)
        self.device.invalidate_recordset()
        self.assertEqual(self.device.current_client_partner_id, self.client)
        self.assertAlmostEqual(self.device.current_client_distance_m, 33, delta=2)

        self._place(19.411, -99.10)
        self.device.invalidate_recordset()
        self.assertFalse(self.device.current_client_geofence_id)
        self.assertEqual(self.device.current_client_distance_m, 0)

    def test_arrival_and_departure_come_from_the_gps_timestamps(self):
        t0 = datetime(2026, 9, 7, 14, 0)
        self._place(19.60, -99.60, t0)
        self._place(19.40, -99.10, t0 + timedelta(minutes=10))
        self._place(19.40, -99.10, t0 + timedelta(minutes=40))
        self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(
            self.device.client_visit_arrival,
            t0 + timedelta(minutes=10),
            "arrival is the first position on the parcel, not the cron's clock",
        )

        self._place(19.60, -99.60, t0 + timedelta(minutes=55))
        self.env["device.device"]._cron_track_client_visits()

        visit = self.device.client_visit_log_id
        self.assertEqual(visit.departure, t0 + timedelta(minutes=55))
        self.assertAlmostEqual(visit.duration_hours, 0.75, places=3)

    def test_silence_closes_the_visit_at_the_last_position(self):
        t0 = datetime.now().replace(microsecond=0) - timedelta(hours=9)
        self._place(19.40, -99.10, t0)
        self._place(19.40, -99.10, t0 + timedelta(hours=1))
        self.env["device.device"]._cron_track_client_visits()
        self.assertFalse(self.device.client_visit_departure)

        self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(self.device.client_visit_departure, t0 + timedelta(hours=1))
        self.assertEqual(
            self.device.client_visit_log_id.departure, t0 + timedelta(hours=1)
        )

    def test_silence_does_not_reopen_the_visit_it_just_closed(self):
        t0 = datetime.now().replace(microsecond=0) - timedelta(hours=9)
        self._place(19.40, -99.10, t0)
        self._place(19.40, -99.10, t0 + timedelta(hours=1))

        for _run in range(6):
            self.env["device.device"]._cron_track_client_visits()

        self.assertEqual(
            len(self._visits()),
            1,
            "a tracker asleep on a parcel must not bank one visit per cron run",
        )
        self.assertEqual(self.device.client_visit_departure, t0 + timedelta(hours=1))

    def test_a_fresh_position_after_the_silence_opens_a_new_visit(self):
        t0 = datetime.now().replace(microsecond=0) - timedelta(hours=9)
        self._place(19.40, -99.10, t0)
        self.env["device.device"]._cron_track_client_visits()
        self.env["device.device"]._cron_track_client_visits()
        self.assertTrue(self.device.client_visit_departure, "closed by the silence")

        now = datetime.now().replace(microsecond=0)
        self._place(19.40, -99.10, now)
        self.device.invalidate_recordset()
        self.env["device.device"]._cron_track_client_visits()

        visits = self._visits()
        self.assertEqual(len(visits), 2)
        self.assertEqual(visits[1].arrival, now)
        self.assertFalse(visits[1].departure)

    def test_speed_today_averages_moving_readings_only(self):
        tz = self.env.tz
        day_start = (
            datetime.combine(datetime.now(tz).date(), time.min, tzinfo=tz)
            .astimezone(UTC)
            .replace(tzinfo=None)
        )
        logs = self.env["device.data.log.gps"]
        for minutes, speed in ((5, 0.0), (15, 60.0), (25, 90.0), (30, 0.0)):
            logs |= logs.create(
                {
                    "device_id": self.device.id,
                    "latitude": 19.40,
                    "longitude": -99.10,
                    "speed": speed,
                    "timestamp": day_start + timedelta(minutes=minutes),
                }
            )
        logs.create(
            {
                "device_id": self.device.id,
                "latitude": 19.40,
                "longitude": -99.10,
                "speed": 150.0,
                "timestamp": day_start - timedelta(hours=1),
            }
        )
        self.device.invalidate_recordset()
        self.assertEqual(self.device.gps_speed_avg_today, 75)
        self.assertEqual(self.device.gps_speed_max_today, 90)
