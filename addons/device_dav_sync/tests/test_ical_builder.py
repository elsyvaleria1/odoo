from datetime import UTC, datetime, timedelta

from ..lib.ical_builder import ICalBuilder
from odoo.addons.device.tests.common import DeviceTransactionCase


class TestICalBuilder(DeviceTransactionCase):
    def setUp(self):
        super().setUp()

        self.builder = ICalBuilder()

        start_dt = datetime.now(UTC)
        stop_dt = start_dt + timedelta(hours=1)

        self.test_event = self.env["calendar.event"].create(
            {
                "name": "Test Meeting",
                "start": start_dt,
                "stop": stop_dt,
                "description": "Test meeting description",
                "location": "Conference Room A",
            }
        )

    def test_event_to_ical(self):
        ical_str = self.builder.event_to_ical(self.test_event, timezone="UTC")

        self.assertIn("BEGIN:VCALENDAR", ical_str)
        self.assertIn("END:VCALENDAR", ical_str)
        self.assertIn("BEGIN:VEVENT", ical_str)
        self.assertIn("END:VEVENT", ical_str)
        self.assertIn("SUMMARY:Test Meeting", ical_str)

    def test_ical_to_event_vals(self):
        ical_str = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//Test//EN
BEGIN:VEVENT
UID:test-event-123@odoo
SUMMARY:New Event
DTSTART:20250106T100000Z
DTEND:20250106T110000Z
DESCRIPTION:Test event description
LOCATION:Meeting Room
END:VEVENT
END:VCALENDAR"""

        vals = self.builder.ical_to_event_vals(ical_str)

        self.assertIn("name", vals)
        self.assertEqual(vals["name"], "New Event")
        self.assertIn("start", vals)
        self.assertIn("stop", vals)
        self.assertIn("description", vals)
        self.assertEqual(vals["location"], "Meeting Room")

    def test_ical_with_timezone(self):
        ical_str = self.builder.event_to_ical(
            self.test_event, timezone="America/New_York"
        )

        self.assertIn("BEGIN:VCALENDAR", ical_str)
        self.assertIn("VEVENT", ical_str)

    def test_all_day_event(self):
        all_day_event = self.env["calendar.event"].create(
            {
                "name": "All Day Event",
                "start": datetime.now(UTC).replace(hour=0, minute=0, second=0),
                "stop": datetime.now(UTC).replace(hour=23, minute=59, second=59),
                "allday": True,
            }
        )

        ical_str = self.builder.event_to_ical(all_day_event, timezone="UTC")

        self.assertIn("DTSTART;VALUE=DATE", ical_str)
