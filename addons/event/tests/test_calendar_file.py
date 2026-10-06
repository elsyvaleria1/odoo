from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import vobject

from odoo.tests import BaseCase, TransactionCase

from odoo.addons.event.tools.calendar import prepare_ics_file


class TestCalendarFilePreparation(BaseCase):
    def test_timezone_transition_and_unicode_content(self):
        content = prepare_ics_file(
            created_at=datetime(2026, 3, 1),
            start=datetime(2026, 3, 8, 7, tzinfo=UTC),
            end=datetime(2026, 3, 8, 8, tzinfo=UTC),
            timezone_name="America/New_York",
            name="Reunión, uno; dos",
            description="First line\nSegunda línea",
            location="Sala México",
        )
        self.assertIsInstance(content, bytes)
        event = vobject.readOne(content.decode()).vevent
        self.assertEqual(event.created.value, datetime(2026, 3, 1, tzinfo=UTC))
        self.assertEqual(event.dtstart.value, datetime(2026, 3, 8, 7, tzinfo=UTC))
        self.assertEqual(event.dtstart.value.utcoffset(), timedelta(hours=-4))
        self.assertEqual(event.dtend.value, datetime(2026, 3, 8, 8, tzinfo=UTC))
        self.assertEqual(event.summary.value, "Reunión, uno; dos")
        self.assertEqual(event.description.value, "First line\nSegunda línea")
        self.assertEqual(event.location.value, "Sala México")

    def test_missing_and_empty_locations_remain_distinct(self):
        values = {
            "created_at": datetime(2026, 1, 1),
            "start": datetime(2026, 1, 2, tzinfo=UTC),
            "end": datetime(2026, 1, 3, tzinfo=UTC),
            "timezone_name": "UTC",
            "name": "Event",
            "description": "",
        }
        without_location = vobject.readOne(prepare_ics_file(**values).decode()).vevent
        empty_location = vobject.readOne(
            prepare_ics_file(**values, location="").decode()
        ).vevent
        self.assertNotIn("location", without_location.contents)
        self.assertEqual(empty_location.location.value, "")


class TestEventCalendarPreparation(TransactionCase):
    def test_recordset_files_keep_their_dates_and_identifiers(self):
        events = self.env["event.event"].create(
            [
                {
                    "name": name,
                    "date_begin": "2026-03-08 07:00:00",
                    "date_end": "2026-03-08 08:00:00",
                    "date_tz": "America/New_York",
                    "address_id": False,
                }
                for name in ("First", "Second")
            ]
        )
        files = events._prepare_ics_files()
        self.assertEqual(set(files), set(events.ids))
        for event in events:
            parsed = vobject.readOne(files[event.id].decode()).vevent
            self.assertEqual(parsed.summary.value, event.name)
            self.assertEqual(parsed.dtstart.value, datetime(2026, 3, 8, 7, tzinfo=UTC))
            self.assertNotIn("location", parsed.contents)

    def test_missing_optional_library_returns_no_files(self):
        with patch("odoo.addons.event.models.event_event.vobject", None):
            self.assertEqual(self.env["event.event"]._prepare_ics_files(), {})
