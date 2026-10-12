from datetime import datetime

from odoo import Command
from odoo.tests import common, tagged


@tagged("post_install", "-at_install")
class TestGeofenceSchedule(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fleet_company = cls.env["res.company"].create({"name": "Fenced fleet"})
        cls.fleet_company.partner_id.tz = "America/Mexico_City"
        cls.env.user.company_ids = [Command.link(cls.fleet_company.id)]
        cls.env.company.partner_id.tz = False
        cls.fence = cls.env["device.geo.fence"].create(
            {
                "name": "Scheduled yard",
                "geofence_type": "circle",
                "center_latitude": 19.40,
                "center_longitude": -99.10,
                "radius": 500.0,
                "company_id": cls.fleet_company.id,
                "schedule_type": "business_hours",
            }
        )

    def test_business_hours_are_the_owners_hours(self):
        self.assertTrue(
            self.fence._is_within_schedule(datetime(2026, 9, 8, 14, 0)),
            "08:00 local on a Tuesday is inside business hours.",
        )

    def test_business_hours_are_shut_outside_them(self):
        self.assertFalse(
            self.fence._is_within_schedule(datetime(2026, 9, 8, 2, 0)),
            "The window used to read this as 02:00 and shut on that instead.",
        )

    def test_the_weekend_is_decided_in_the_owners_timezone(self):
        self.assertFalse(
            self.fence._is_within_schedule(datetime(2026, 9, 7, 2, 0)),
            "Sunday is not a business day, whatever the UTC date says.",
        )

    def test_always_needs_no_clock_at_all(self):
        self.fence.schedule_type = "always"

        self.assertTrue(self.fence._is_within_schedule(datetime(2026, 9, 8, 2, 0)))

    def test_a_custom_window_is_read_in_the_owners_hours(self):
        self.fence.write(
            {
                "schedule_type": "custom",
                "schedule_time_from": 6.0,
                "schedule_time_to": 7.5,
            }
        )

        self.assertTrue(self.fence._is_within_schedule(datetime(2026, 9, 8, 12, 30)))
        self.assertFalse(self.fence._is_within_schedule(datetime(2026, 9, 8, 14, 0)))

    def test_a_custom_window_honours_its_weekdays(self):
        monday = self.env.ref("device_gps_geoengine.weekday_0_monday")
        self.fence.write(
            {
                "schedule_type": "custom",
                "schedule_time_from": 6.0,
                "schedule_time_to": 7.5,
                "schedule_weekday_ids": [Command.set(monday.ids)],
            }
        )

        self.assertTrue(self.fence._is_within_schedule(datetime(2026, 9, 7, 12, 30)))
        self.assertFalse(self.fence._is_within_schedule(datetime(2026, 9, 8, 12, 30)))

    def test_a_company_less_fence_falls_back_to_the_acting_company(self):
        self.fence.company_id = False

        self.assertEqual(
            self.fence._schedule_local_now(datetime(2026, 9, 8, 14, 0)).hour,
            14,
            "No owning company and no acting timezone leaves UTC.",
        )
