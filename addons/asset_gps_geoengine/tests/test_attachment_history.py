from datetime import date, datetime

from freezegun import freeze_time

from odoo.libs.json import dumps as json_dumps
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAttachmentGeography(TransactionCase):
    def setUp(self):
        super().setUp()
        with freeze_time("2026-09-01"):
            self.device = self.env["device.device"].create(
                {
                    "name": "Moving tracker",
                    "identifier": "moving-history",
                    "device_category_id": self.env.ref("device.device_category_gps").id,
                }
            )
            self.first = self.env["resource.resource"].create(
                {
                    "name": "Earlier equipment",
                    "kind_id": self.env.ref("base.kind_machinery").id,
                    "gps_device_id": self.device.id,
                    "tz": "UTC",
                }
            )
            self.second = self.first.copy({"name": "Later equipment"})
        self.env.cr.execute(
            "UPDATE device_device SET create_date = %s WHERE id = %s",
            [datetime(2026, 9, 1), self.device.id],
        )
        self.device.invalidate_recordset(["create_date"])

    def _log(self, timestamp, speed=0, longitude=-99.6):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": timestamp,
                "speed": speed,
                "latitude": 19.3,
                "longitude": longitude,
            }
        )

    def _move(self, at="2026-09-05 00:00:00"):
        with freeze_time(at):
            self.device.asset_id = self.second

    def test_stops_split_at_reassignment_and_keep_the_previous_asset(self):
        self._log("2026-09-04 23:40:00")
        self._log("2026-09-04 23:50:00")
        self._move()
        self._log("2026-09-05 00:00:00")
        self._log("2026-09-05 00:10:00")
        self._log("2026-09-05 00:20:00", speed=30)
        report = self.env["device.gps.stop"]
        report._refresh(date(2026, 9, 4), date(2026, 9, 5), devices=self.device)
        stops = report.search(
            [("device_id", "=", self.device.id), ("kind", "=", "stop")], order="arrival"
        )
        self.assertEqual(stops.mapped("asset_id"), self.first | self.second)
        self.assertEqual(stops[0].departure, datetime(2026, 9, 5))
        self.assertFalse(stops[0].ongoing)
        self.assertAlmostEqual(stops[0].duration_hours, 1 / 3)
        self.assertEqual(stops[1].arrival, datetime(2026, 9, 5))
        report._refresh(date(2026, 9, 4), date(2026, 9, 5), devices=self.device)
        self.assertEqual(
            report.search_count(
                [("device_id", "=", self.device.id), ("kind", "=", "stop")]
            ),
            2,
        )

    def test_speed_reports_split_a_device_day_and_burst_between_assets(self):
        self._log("2026-09-05 11:59:30", speed=90)
        self._move("2026-09-05 12:00:00")
        self._log("2026-09-05 12:00:00", speed=110)
        self.env.flush_all()
        days = self.env["device.gps.speed.day"].search(
            [("device_id", "=", self.device.id)], order="first_seen"
        )
        events = self.env["device.gps.speed.event"].search(
            [("device_id", "=", self.device.id)], order="start"
        )
        self.assertEqual(days.mapped("asset_id"), self.first | self.second)
        self.assertEqual(days.mapped("positions"), [1, 1])
        self.assertEqual(events.mapped("asset_id"), self.first | self.second)
        self.assertEqual(events.mapped("positions"), [1, 1])

    def test_asset_trail_after_detachment_excludes_the_next_assets_positions(self):
        self._log("2026-09-03 12:00:00", longitude=-99.60)
        self._log("2026-09-03 12:01:00", longitude=-99.61)
        self._move()
        self._log("2026-09-06 12:00:00", longitude=-99.62)
        self._log("2026-09-06 12:01:00", longitude=-99.63)
        wizard = self.env["wizard.device.device.view.trail"].create(
            {
                "selection_mode": "asset",
                "asset_ids": self.first.ids,
                "date_from": "2026-09-01",
                "date_to": "2026-09-07",
                "group_by": "source",
            }
        )
        self.assertEqual(wizard.resolved_device_ids, self.device)
        action = wizard.action_generate_trails()
        trail = self.env[action["res_model"]].search(action["domain"])
        self.assertEqual(trail.asset_id, self.first)
        self.assertEqual(trail.point_count, 2)
        self.assertEqual(trail.date_to, datetime(2026, 9, 3, 12, 1))

    def test_no_signal_dimensions_use_the_attachment_of_that_day(self):
        self._move()
        report = self.env["device.gps.stop"]
        report._refresh(date(2026, 9, 3), date(2026, 9, 6), devices=self.device)
        rows = report.search(
            [("device_id", "=", self.device.id), ("kind", "=", "no_signal")],
            order="date",
        )
        self.assertEqual(rows.mapped("asset_id"), self.first | self.second)
        self.assertEqual(
            rows.filtered(lambda row: row.date == date(2026, 9, 3)).asset_id, self.first
        )
        self.assertEqual(
            rows.filtered(lambda row: row.date == date(2026, 9, 6)).asset_id,
            self.second,
        )

    def test_client_visit_dimensions_and_trip_speeds_follow_historical_target(self):
        employees = self.env["hr.employee"].create(
            [
                {"name": "Earlier visit operator", "company_id": self.env.company.id},
                {"name": "Later visit operator", "company_id": self.env.company.id},
            ]
        )
        with freeze_time("2026-09-01"):
            self.first.operator_employee_id = employees[0]
            self.second.operator_employee_id = employees[1]
        self.first.tz = "Asia/Tokyo"
        partner = self.env["res.partner"].create({"name": "Historical visit customer"})
        fence = self.env["device.geo.fence"].create(
            {
                "name": "Historical visit parcel",
                "partner_id": partner.id,
                "area_type": "parcel",
                "geofence_type": "polygon",
                "schedule_type": "always",
                "polygon_points": json_dumps(
                    [[19.29, -99.61], [19.31, -99.61], [19.31, -99.59], [19.29, -99.59]]
                ),
            }
        )
        self._log("2026-09-02 10:00:00", speed=130)
        self._log("2026-09-02 16:00:00", speed=80)
        self._log("2026-09-03 02:00:00", speed=20)
        Visit = self.env["device.client.visit"]
        earlier = Visit.create(
            {
                "device_id": self.device.id,
                "partner_id": partner.id,
                "geofence_id": fence.id,
                "arrival": "2026-09-03 03:00:00",
                "departure": "2026-09-03 03:30:00",
            }
        )
        self._log("2026-09-05 11:00:00", speed=150)
        self._move("2026-09-05 12:00:00")
        self._log("2026-09-05 12:05:00", speed=40)
        later = Visit.create(
            {
                "device_id": self.device.id,
                "partner_id": partner.id,
                "geofence_id": fence.id,
                "arrival": "2026-09-05 12:10:00",
                "departure": "2026-09-05 12:30:00",
            }
        )
        self.assertEqual(earlier.asset_id, self.first)
        self.assertEqual(earlier.operator_id, employees[0])
        self.assertEqual(later.asset_id, self.second)
        self.assertEqual(later.operator_id, employees[1])
        self.assertEqual(earlier.trip_speed_max, 80)
        self.assertEqual(earlier.trip_speed_min, 20)
        self.assertEqual(earlier.trip_speed_avg, 50)
        self.assertEqual(later.trip_speed_max, 40)
