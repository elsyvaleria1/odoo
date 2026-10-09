from datetime import datetime
from unittest.mock import patch

import requests

from odoo.libs.json import dumps
from odoo.tests import tagged

from odoo.addons.calendar_google.tests.test_sync_common import TestSyncGoogle
from odoo.addons.calendar_google.utils.calendar_google import GoogleCalendarService
from odoo.addons.calendar_google.utils.google_event import GoogleEvent
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers


@tagged("odoo2google")
@patch.object(
    CalendarSyncUsers,
    "_calendar_sync_connection",
    lambda user, code: code == "google" and "dummy-token",
)
class TestSyncFailures(TestSyncGoogle):
    """What Google refuses or loses, through the engine."""

    def _http_error(self, status, message):
        response = requests.Response()
        response.status_code = status
        response._content = dumps({"error": {"message": message}}).encode()
        return requests.HTTPError(response=response)

    def _event(self):
        return (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(
                {
                    "name": "Event",
                    "start": datetime(2030, 1, 15, 8, 0),
                    "stop": datetime(2030, 1, 15, 18, 0),
                    "user_id": self.organizer_user.id,
                    "partner_ids": [(4, self.organizer_user.partner_id.id)],
                }
            )
        )

    def _run(self):
        account = self.organizer_user._calendar_sync_account("google")
        account.sync_token = account.sync_token or "a-token"
        with patch.object(
            GoogleCalendarService,
            "get_events",
            return_value=(GoogleEvent([]), "next-token", ()),
        ):
            self.organizer_user._calendar_sync_as_owner()._calendar_sync_run("google")
        self.push_google()

    def test_a_refused_insert_is_noted_once_and_not_sent_again(self):
        """Google refused an insert with a 403: the event was noted as not
        synchronized, and every run sent it again and noted it again, because
        a record with no Google id was always a candidate."""
        sent = []

        def insert(service, values, connection=None, timeout=None, need_video_call=1):
            sent.append(values["id"])
            raise self._http_error(403, "forbidden for this calendar")

        with patch.object(GoogleCalendarService, "insert", insert):
            event = self._event()
            self.push_google()
            self._run()
            self._run()

        self.assertEqual(len(sent), 1)
        notes = event.message_ids.filtered(
            lambda message: "refused this event" in (message.body or "")
        )
        self.assertEqual(len(notes), 1)
        self.assertIn("forbidden for this calendar", notes.body)

    def test_an_insert_whose_answer_was_lost_is_not_inserted_twice(self):
        """Google inserted the event but its answer never came back: the next
        run inserted it again under a new id. The retry sends the same id, which
        Google refuses as existing, and the event takes it."""
        sent = []

        def insert(service, values, connection=None, timeout=None, need_video_call=1):
            sent.append(values["id"])
            if len(sent) == 1:
                raise requests.ConnectionError("the answer was lost")
            raise self._http_error(409, "The requested identifier already exists.")

        with patch.object(GoogleCalendarService, "insert", insert):
            event = self._event()
            self.push_google()
            self.assertFalse(self.google_id(event))
            self._run()

        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0], sent[1], "the retry sends the same id")
        self.assertEqual(self.google_id(event), sent[0])
