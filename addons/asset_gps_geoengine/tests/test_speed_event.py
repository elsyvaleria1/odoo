from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from freezegun import freeze_time

from odoo.libs.json import dumps as json_dumps
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestSpeedEvent(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.config = self.env["device.profile"].create(
            {
                "name": "Speed Test Config",
                "speed_limit_warning": 80.0,
                "speed_limit_alert": 100.0,
                "speed_limit_critical": 120.0,
            }
        )
        self.device = self.env["device.device"].create(
            {
                "name": "Speed Tracker",
                "identifier": "SPEED-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "imei": "TEST-IMEI-SPEED-001",
                "device_category_id": self.env.ref("device.device_category_gps").id,
            }
        )
        self.client = self.env["res.partner"].create({"name": "Fast Client"})
        self.env["device.geo.fence"].create(
            {
                "name": "Fast Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": self.client.id,
                "polygon_points": json_dumps(
                    [[19.39, -99.11], [19.41, -99.11], [19.41, -99.09], [19.39, -99.09]]
                ),
            }
        )

    def _drive(self, t0, speeds, step=timedelta(seconds=30), lat=19.4103):
        for i, speed in enumerate(speeds):
            self.env["device.data.log.gps"].create(
                {
                    "device_id": self.device.id,
                    "timestamp": t0 + i * step,
                    "latitude": lat,
                    "longitude": -99.10 + i * 0.001,
                    "speed": speed,
                }
            )

    def _raise_for_this_device(self):
        return (
            self.env["device.gps.speed.alert"]
            ._cron_raise_critical()
            .filtered(lambda alert: alert.device_id == self.device)
        )

    def _events(self):
        self.env.flush_all()
        return self.env["device.gps.speed.event"].search(
            [("device_id", "=", self.device.id)], order="start"
        )

    def test_bursts_are_split_by_gap_and_graded_by_peak(self):
        t0 = datetime(2026, 9, 7, 15, 0)
        self._drive(t0, [60, 85, 95, 125, 70])
        self._drive(t0 + timedelta(minutes=10), [90, 88, 50])

        events = self._events()
        self.assertEqual(len(events), 2)
        first, second = events
        self.assertEqual(first.level, "critical")
        self.assertEqual(first.speed_max, 125)
        self.assertEqual(first.speed_limit, 120)
        self.assertEqual(first.positions, 3)
        self.assertEqual(first.start, t0 + timedelta(seconds=30))
        self.assertEqual(first.end, t0 + timedelta(seconds=90))
        self.assertEqual(second.level, "warning")
        self.assertEqual(second.positions, 2)

    def test_place_names_the_nearest_client_parcel(self):
        self._drive(datetime(2026, 9, 7, 15, 0), [95, 96])
        event = self._events()
        self.assertEqual(event.nearby_partner_id, self.client)
        self.assertIn("Fast Parcel (Fast Client)", event.place)
        self.assertLess(event.nearby_distance_m, 60)

    def test_nothing_below_the_warning_limit(self):
        self._drive(datetime(2026, 9, 7, 15, 0), [40, 79, 80, 60])
        self.assertFalse(self._events())

    def test_daily_profile_has_max_min_moving_and_avg(self):
        t0 = datetime(2026, 9, 7, 15, 0)
        self._drive(t0, [0, 40, 130, 60, 0])
        self.env.flush_all()
        day = self.env["device.gps.speed.day"].search(
            [("device_id", "=", self.device.id), ("date", "=", t0.date())]
        )
        self.assertEqual(len(day), 1)
        self.assertEqual(day.speed_max, 130)
        self.assertEqual(day.speed_min, 40, "stops do not count as the minimum")
        self.assertAlmostEqual(day.speed_avg, (40 + 130 + 60) / 3, delta=1)
        self.assertTrue(day.over_critical)

    def test_visit_trip_speed_covers_the_way_to_the_parcel(self):
        t0 = datetime(2026, 9, 7, 8, 0)
        client = self.env["res.partner"].create({"name": "Trip Client"})
        parcel = self.env["device.geo.fence"].create(
            {
                "name": "Trip Parcel",
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "partner_id": client.id,
                "polygon_points": json_dumps(
                    [[20.0, -100.0], [20.01, -100.0], [20.01, -99.99], [20.0, -99.99]]
                ),
            }
        )
        self._drive(t0, [30, 110, 50], lat=19.9)
        visit = self.env["device.client.visit"].create(
            {
                "device_id": self.device.id,
                "partner_id": client.id,
                "geofence_id": parcel.id,
                "arrival": t0 + timedelta(minutes=5),
            }
        )
        self.assertEqual(visit.trip_speed_max, 110)
        self.assertEqual(visit.trip_speed_min, 30)

    def test_critical_burst_raises_one_alert_to_the_manager(self):
        manager = self.env["res.users"].create(
            {
                "name": "Fleet Boss",
                "login": "fleet.boss@test.example",
                "tz": "Pacific/Kiritimati",
            }
        )
        boss = self.env["hr.employee"].create(
            {"name": "Fleet Boss", "user_id": manager.id}
        )
        driver = self.env["hr.employee"].create(
            {"name": "Fast Driver", "parent_id": boss.id}
        )
        product = self.env["product.product"].create(
            {
                "name": "Speed Truck",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": self.env.ref("base.kind_vehicle").id,
                "company_id": self.env.company.id,
            }
        )
        with freeze_time(datetime.now() - timedelta(hours=1)):
            self.env["product.trace"].create(
                {
                    "name": "SPD-001",
                    "product_id": product.id,
                    "gps_device_id": self.device.id,
                    "operator_id": driver.id,
                }
            )
        t0 = datetime.now() - timedelta(minutes=30)
        self._drive(t0, [90, 130, 125, 60])
        self.env.flush_all()

        raised = self._raise_for_this_device()
        self.assertEqual(len(raised), 1)
        self.assertEqual(raised.operator_id, driver)
        self.assertEqual(raised.speed_max, 130)
        self.assertEqual(raised.user_id, manager)
        self.assertEqual(raised.activity_id.user_id, manager)
        self.assertIn("130", raised.activity_id.summary)

        local = (
            raised.start.replace(tzinfo=UTC)
            .astimezone(ZoneInfo("Pacific/Kiritimati"))
            .strftime("%d/%m/%Y %H:%M")
        )
        self.assertNotEqual(local, raised.start.strftime("%d/%m/%Y %H:%M"))
        self.assertIn(
            local,
            raised.activity_id.note,
            "the note must read the burst in the recipient's timezone",
        )

        self.assertFalse(
            self._raise_for_this_device(), "the same burst is not alerted twice"
        )

    def test_ongoing_burst_waits_until_it_is_over(self):
        t0 = datetime.now() - timedelta(minutes=1)
        self._drive(t0, [130, 135])
        self.env.flush_all()
        self.assertFalse(self._raise_for_this_device())
