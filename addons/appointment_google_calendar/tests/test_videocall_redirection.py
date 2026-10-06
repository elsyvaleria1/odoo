import re
from datetime import datetime
from unittest.mock import patch

from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestGoogleMeetRedirection(TransactionCase):
    def test_a_google_meet_redirection_names_a_token_the_calendar_owner_minted(self):
        organizer = new_test_user(
            self.env, login="gmeet_organizer", groups="base.group_user"
        )
        event = self.env["calendar.event"].create(
            {
                "name": "Google Meet appointment",
                "start": datetime(2026, 10, 1, 9),
                "stop": datetime(2026, 10, 1, 10),
                "user_id": organizer.id,
                "videocall_location": "https://meet.google.com/abc-defg-hij",
            }
        )
        event.write({"access_token": False})
        self.assertEqual(event.videocall_source, "google_meet")

        event_class = type(event)
        original = event_class._update_access_token
        minted = []

        def spy(events):
            minted.extend(events.ids)
            return original(events)

        with (
            patch.object(
                type(organizer), "is_google_calendar_synced", lambda user: True
            ),
            patch.object(event_class, "_update_access_token", spy),
        ):
            event.invalidate_recordset(["videocall_redirection"])
            redirection = event.videocall_redirection

        self.assertEqual(minted, event.ids)
        event.invalidate_recordset(["access_token"])
        self.assertRegex(event.access_token, re.compile(r"^[0-9a-f]{32}$"))
        self.assertTrue(
            redirection.endswith(f"/calendar/videocall/{event.access_token}")
        )
