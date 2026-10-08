from unittest.mock import patch

from freezegun import freeze_time

from odoo.libs.json import dumps as json_dumps
from odoo.tests import users

from odoo.addons.calendar_microsoft.tests.common import (
    TestCommon,
    _modified_date_in_the_future,
    authorize_microsoft_calendar,
    mock_get_connection,
)
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    MicrosoftCalendarService,
)
from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers


@patch.object(CalendarSyncUsers, "_calendar_sync_connection", mock_get_connection)
class TestAnswerEvents(TestCommon):
    def setUp(self):
        super().setUp()

        # a simple event
        self.simple_event = self.env["calendar.event"].search(
            [("name", "=", "simple_event")]
        )
        if not self.simple_event:
            self.simple_event = self.link_microsoft(
                self.env["calendar.event"]
                .with_user(self.organizer_user)
                .create(self.simple_event_values),
                self.organizer_user,
                "123",
                "456",
            )

    @patch.object(MicrosoftCalendarService, "_get_single_event")
    @patch.object(MicrosoftCalendarService, "answer")
    def test_attendee_accepts_event_from_odoo_calendar(
        self, mock_answer, mock_get_single_event
    ):
        attendee = self.env["calendar.attendee"].search(
            [
                ("event_id", "=", self.simple_event.id),
                ("partner_id", "=", self.attendee_user.partner_id.id),
            ]
        )

        # the attendee's copy has an id of its own, found by its iCalendar UID
        mock_get_single_event.return_value = (
            True,
            {"value": [{"id": "attendee_123", "iCalUId": "456"}]},
        )
        attendee.with_user(self.attendee_user).do_accept()
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        mock_answer.assert_called_once_with(
            "attendee_123",
            "accept",
            {"comment": "", "sendResponse": True},
            connection=mock_get_connection(self.attendee_user),
            timeout=5,
        )
        self.assertEqual(
            self.microsoft_id(self.simple_event, self.attendee_user), "attendee_123"
        )

    @patch.object(MicrosoftCalendarService, "_get_single_event")
    @patch.object(MicrosoftCalendarService, "answer")
    def test_attendee_declines_event_from_odoo_calendar(
        self, mock_answer, mock_get_single_event
    ):
        attendee = self.env["calendar.attendee"].search(
            [
                ("event_id", "=", self.simple_event.id),
                ("partner_id", "=", self.attendee_user.partner_id.id),
            ]
        )
        # the attendee's copy has an id of its own, found by its iCalendar UID
        mock_get_single_event.return_value = (
            True,
            {"value": [{"id": "attendee_123", "iCalUId": "456"}]},
        )
        attendee.with_user(self.attendee_user).do_decline()
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()
        mock_answer.assert_called_once_with(
            "attendee_123",
            "decline",
            {"comment": "", "sendResponse": True},
            connection=mock_get_connection(self.attendee_user),
            timeout=5,
        )
        self.assertEqual(
            self.microsoft_id(self.simple_event, self.attendee_user), "attendee_123"
        )

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_attendee_accepts_event_from_outlook_calendar(self, mock_get_events):
        """
        In his Outlook calendar, the attendee accepts the event and sync with his odoo calendar.
        """
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        self.simple_event_from_outlook_organizer,
                        attendees=[
                            {
                                "type": "required",
                                "status": {
                                    "response": "accepted",
                                    "time": "0001-01-01T00:00:00Z",
                                },
                                "emailAddress": {
                                    "name": self.attendee_user.display_name,
                                    "address": self.attendee_user.email,
                                },
                            }
                        ],
                        lastModifiedDateTime=_modified_date_in_the_future(
                            self.simple_event
                        ),
                    )
                ]
            ),
            None,
        )
        self.attendee_user.with_user(self.attendee_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        attendee = self.env["calendar.attendee"].search(
            [
                ("event_id", "=", self.simple_event.id),
                ("partner_id", "=", self.attendee_user.partner_id.id),
            ]
        )
        self.assertEqual(attendee.state, "accepted")

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_attendee_accepts_event_from_outlook_calendar_synced_by_organizer(
        self, mock_get_events
    ):
        """
        In his Outlook calendar, the attendee accepts the event and the organizer syncs his odoo calendar.
        """
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        self.simple_event_from_outlook_organizer,
                        attendees=[
                            {
                                "type": "required",
                                "status": {
                                    "response": "accepted",
                                    "time": "0001-01-01T00:00:00Z",
                                },
                                "emailAddress": {
                                    "name": self.attendee_user.display_name,
                                    "address": self.attendee_user.email,
                                },
                            }
                        ],
                        lastModifiedDateTime=_modified_date_in_the_future(
                            self.simple_event
                        ),
                    )
                ]
            ),
            None,
        )
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        attendee = self.env["calendar.attendee"].search(
            [
                ("event_id", "=", self.simple_event.id),
                ("partner_id", "=", self.attendee_user.partner_id.id),
            ]
        )
        self.assertEqual(attendee.state, "accepted")

    def test_attendee_declines_event_from_outlook_calendar(self):
        """
        In his Outlook calendar, the attendee declines the event leading to automatically
        delete this event (that's the way Outlook handles it ...)

        LIMITATION:

        But, as there is no way to get the iCalUId to identify the corresponding Odoo event,
        there is no way to update the attendee status to "declined".
        """

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_attendee_declines_event_from_outlook_calendar_synced_by_organizer(
        self, mock_get_events
    ):
        """
        In his Outlook calendar, the attendee declines the event leading to automatically
        delete this event (that's the way Outlook handles it ...)
        """
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        self.simple_event_from_outlook_organizer,
                        attendees=[
                            {
                                "type": "required",
                                "status": {
                                    "response": "declined",
                                    "time": "0001-01-01T00:00:00Z",
                                },
                                "emailAddress": {
                                    "name": self.attendee_user.display_name,
                                    "address": self.attendee_user.email,
                                },
                            }
                        ],
                        lastModifiedDateTime=_modified_date_in_the_future(
                            self.simple_event
                        ),
                    )
                ]
            ),
            None,
        )
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        attendee = self.env["calendar.attendee"].search(
            [
                ("event_id", "=", self.simple_event.id),
                ("partner_id", "=", self.attendee_user.partner_id.id),
            ]
        )
        self.assertEqual(attendee.state, "declined")

    @users("admin")
    def test_sync_data_with_stopped_sync(self):
        self.authenticate(self.env.user.login, self.env.user.login)
        self.env.ref(
            "integration_microsoft.service_microsoft"
        ).sudo()._set_oauth_client(
            "test_microsoft_calendar_client_id", "a-secret", company=False
        )
        authorize_microsoft_calendar(self.env.user)
        self.env.user.calendar_sync_stop("microsoft")
        payload = {"params": {"model": "calendar.event"}}
        # Sending the request to the sync_data
        response = self.url_open(
            "/calendar_sync/microsoft/sync_data",
            data=json_dumps(payload),
            headers={"Content-Type": "application/json"},
        ).json()
        # the status must be sync_stopped
        self.assertEqual(response["result"]["status"], "sync_stopped")

    @patch.object(MicrosoftCalendarService, "patch")
    @patch.object(MicrosoftCalendarService, "_get_single_event")
    @patch.object(MicrosoftCalendarService, "answer")
    def test_answer_event_with_external_organizer(
        self, mock_answer, mock_get_single_event, mock_patch
    ):
        """An invitation from someone outside Odoo is answered from the
        answering user's own calendar, under its own id there."""
        self.simple_event.write({"user_id": False, "partner_id": False})
        attendee = self.simple_event.attendee_ids.filtered(
            lambda attendee: attendee.partner_id == self.organizer_user.partner_id
        )
        attendee.state = "needsAction"
        self.call_post_commit_hooks()

        attendee.with_user(self.organizer_user).do_accept()
        self.call_post_commit_hooks()
        mock_answer.assert_called_once_with(
            "123",
            "accept",
            {"comment": "", "sendResponse": True},
            connection=mock_get_connection(self.organizer_user),
            timeout=5,
        )

        attendee.with_user(self.organizer_user).do_decline()
        self.call_post_commit_hooks()
        mock_answer.assert_called_with(
            "123",
            "decline",
            {"comment": "", "sendResponse": True},
            connection=mock_get_connection(self.organizer_user),
            timeout=5,
        )
        mock_get_single_event.assert_not_called()
