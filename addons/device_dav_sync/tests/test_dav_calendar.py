from datetime import UTC, datetime, timedelta

from odoo.addons.device.tests.common import DeviceTransactionCase


class TestDAVCalendar(DeviceTransactionCase):
    def setUp(self):
        super().setUp()

        self.test_user = self.env["res.users"].create(
            {
                "name": "Test User",
                "login": "test_calendar_user",
                "email": "test@example.com",
            }
        )

        start_dt = datetime.now(UTC)
        stop_dt = start_dt + timedelta(hours=1)

        self.event1 = self.env["calendar.event"].create(
            {
                "name": "Event 1",
                "start": start_dt,
                "stop": stop_dt,
                "user_id": self.test_user.id,
            }
        )
        self.event2 = self.env["calendar.event"].create(
            {
                "name": "Event 2",
                "start": start_dt + timedelta(days=1),
                "stop": stop_dt + timedelta(days=1),
                "user_id": self.test_user.id,
            }
        )

    def test_create_calendar(self):
        calendar = self.env["dav.calendar"].create(
            {
                "name": "Test Calendar",
                "user_id": self.test_user.id,
                "description": "Test calendar for unit testing",
                "color": "#FF0000",
            }
        )

        self.assertEqual(calendar.name, "Test Calendar")
        self.assertEqual(calendar.user_id, self.test_user)
        self.assertEqual(calendar.color, "#FF0000")
        self.assertTrue(calendar.active)

    def test_get_events(self):
        calendar = self.env["dav.calendar"].create(
            {
                "name": "Test Calendar",
                "user_id": self.test_user.id,
            }
        )

        events = calendar.get_events()

        self.assertIsInstance(events, type(self.env["calendar.event"]))

    def test_ctag_computation(self):
        calendar = self.env["dav.calendar"].create(
            {
                "name": "Test Calendar",
                "user_id": self.test_user.id,
            }
        )

        ctag1 = calendar.ctag
        self.assertIsNotNone(ctag1)

        self.assertIsInstance(ctag1, str)
