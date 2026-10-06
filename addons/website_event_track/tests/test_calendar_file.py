from datetime import UTC, datetime
from unittest.mock import patch

import vobject

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTrackCalendarPreparation(TransactionCase):
    def test_track_calendar_keeps_reminder_dates_and_optional_absence(self):
        event = self.env["event.event"].create(
            {
                "name": "Conference",
                "date_begin": "2026-03-08 07:00:00",
                "date_end": "2026-03-08 08:00:00",
                "date_tz": "America/New_York",
                "address_id": False,
            }
        )
        track = self.env["event.track"].create(
            {"name": "Talk", "event_id": event.id, "date": False}
        )
        content = track._prepare_ics_files()[track.id]
        self.assertIsInstance(content, bytes)
        parsed = vobject.readOne(content.decode()).vevent
        self.assertEqual(parsed.summary.value, track.name)
        self.assertEqual(parsed.dtstart.value, datetime(2026, 3, 8, 7, tzinfo=UTC))
        self.assertEqual(parsed.dtend.value, datetime(2026, 3, 8, 8, tzinfo=UTC))
        self.assertNotIn("location", parsed.contents)
        with patch("odoo.addons.website_event_track.models.event_track.vobject", None):
            self.assertEqual(track._prepare_ics_files(), {track.id: None})
