import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, patch

from dateutil.parser import parse
from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import UserError, ValidationError

from odoo.addons.calendar_microsoft.tests.common import (
    TestCommon,
    _modified_date_in_the_future,
    mock_get_connection,
)
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    MicrosoftCalendarService,
)
from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers

_logger = logging.getLogger(__name__)


@patch.object(CalendarSyncUsers, "_calendar_sync_connection", mock_get_connection)
class TestUpdateEvents(TestCommon):
    def setUp(self):
        super().setUp()
        self.create_events_for_tests()

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_odoo_simple_event_without_sync(self, mock_patch):

        self.organizer_user._calendar_sync_account("microsoft").stopped = True

        self.simple_event.write({"name": "my new simple event"})
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        mock_patch.assert_not_called()

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_simple_event_with_sync_config_paused(self, mock_patch):
        self.organizer_user._calendar_sync_account("microsoft").stopped = False
        self.env["calendar.sync.account"]._set_paused("microsoft", True)

        self.simple_event.with_user(self.organizer_user).write(
            {"name": "renamed while paused"}
        )
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        mock_patch.assert_not_called()
        self.assertTrue(self.awaits_push(self.simple_event))

    @patch.object(MicrosoftCalendarService, "patch")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_an_attendees_synchronization_keeps_the_organizers_id(
        self, mock_get_events, mock_patch
    ):
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        self.simple_event_from_outlook_attendee,
                        id="attendee_123",
                        lastModifiedDateTime=_modified_date_in_the_future(
                            self.simple_event
                        ),
                    )
                ]
            ),
            None,
        )
        mock_patch.return_value = {}
        self.sync_microsoft(self.attendee_user)

        self.assertEqual(
            self.microsoft_id(self.simple_event, self.attendee_user), "attendee_123"
        )
        self.assertEqual(
            self.microsoft_id(self.simple_event, self.organizer_user), "123"
        )

        self.simple_event.with_user(self.organizer_user).write({"name": "renamed"})
        self.call_post_commit_hooks()
        self.assert_patched(
            mock_patch, "123", {"subject": "renamed"}, self.organizer_user
        )

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_simple_event_from_odoo(self, mock_patch):

        mock_patch.return_value = {}

        res = self.simple_event.with_user(self.organizer_user).write(
            {"name": "my new simple event"}
        )
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertTrue(res)
        self.assert_patched(
            mock_patch,
            "123",
            {"subject": "my new simple event", "isOnlineMeeting": None},
            self.organizer_user,
        )
        self.assertEqual(self.simple_event.name, "my new simple event")

    @patch.object(MicrosoftCalendarService, "patch")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_an_edit_whose_push_was_lost_is_sent_by_a_later_run(
        self, mock_get_events, mock_patch
    ):
        mock_get_events.return_value = (MicrosoftEvent([]), "next-token")
        mock_patch.return_value = {}
        account = self.organizer_user._calendar_sync_account("microsoft")
        account.write(
            {"sync_token": "a-token", "last_sync_date": datetime(2021, 9, 22, 9, 0)}
        )
        with self.mock_datetime_and_now("2021-09-22 10:00:00"):
            self.simple_event.with_user(self.organizer_user).write(
                {"name": "edited while Outlook was down"}
            )
        self.env.cr.postcommit.clear()
        self.assertTrue(self.awaits_push(self.simple_event))

        with self.mock_datetime_and_now("2021-09-22 11:00:00"):
            self.organizer_user.with_user(
                self.organizer_user
            ).sudo()._calendar_sync_run("microsoft")
            self.call_post_commit_hooks()

        mock_patch.assert_called_once_with(
            self.held_id(self.simple_event),
            ANY,
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )
        self.assertEqual(
            mock_patch.call_args.args[1]["subject"], "edited while Outlook was down"
        )

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_simple_event_from_odoo_attendee_calendar(self, mock_patch):

        mock_patch.return_value = {}

        res = self.simple_event.with_user(self.attendee_user).write(
            {"name": "my new simple event"}
        )
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertTrue(res)
        self.assert_patched(
            mock_patch,
            "123",
            {"subject": "my new simple event", "isOnlineMeeting": None},
            self.organizer_user,
        )
        self.assertEqual(self.simple_event.name, "my new simple event")

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_one_event_of_recurrence_from_odoo(self, mock_patch):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_name = "my specific event in recurrence"
        modified_event_id = 4

        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.organizer_user)
            .write(
                {
                    "recurrence_update": "this",
                    "name": new_name,
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events[modified_event_id].invalidate_recordset()

        self.assertTrue(res)
        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[modified_event_id]),
            {"seriesMasterId": "REC123", "type": "exception", "subject": new_name},
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )
        self.assertEqual(self.recurrent_events[modified_event_id].name, new_name)
        self.assertEqual(
            self.recurrent_events[modified_event_id].follow_recurrence, True
        )

        for i in range(self.recurrent_events_count):
            if i != modified_event_id:
                self.assertNotEqual(self.recurrent_events[i].name, new_name)

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_start_of_one_event_of_recurrence_from_odoo(self, mock_patch):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_date = datetime(2021, 9, 29, 10, 0, 0)
        modified_event_id = 4

        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.organizer_user)
            .write(
                {
                    "recurrence_update": "this",
                    "start": new_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events[modified_event_id].invalidate_recordset()

        self.assertTrue(res)
        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[modified_event_id]),
            {
                "seriesMasterId": "REC123",
                "type": "exception",
                "start": {
                    "dateTime": new_date.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                },
                "end": {
                    "dateTime": (new_date + timedelta(hours=1))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "timeZone": "Europe/London",
                },
                "isAllDay": False,
            },
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )
        self.assertEqual(self.recurrent_events[modified_event_id].start, new_date)
        self.assertEqual(
            self.recurrent_events[modified_event_id].follow_recurrence, False
        )

        for i in range(self.recurrent_events_count):
            if i != modified_event_id:
                self.assertNotEqual(self.recurrent_events[i].start, new_date)
                self.assertEqual(self.recurrent_events[i].follow_recurrence, True)

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_start_of_one_event_of_recurrence_from_odoo_with_overlap(
        self, mock_patch
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_date = datetime(2021, 9, 27, 10, 0, 0)
        modified_event_id = 4

        with self.assertRaises(UserError):
            self.recurrent_events[modified_event_id].with_user(
                self.organizer_user
            ).write(
                {
                    "recurrence_update": "this",
                    "start": new_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            self.call_post_commit_hooks()
            self.recurrent_events.invalidate_recordset()

        mock_patch.assert_not_called()

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_one_event_of_recurrence_from_odoo_attendee_calendar(
        self, mock_patch
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_name = "my specific event in recurrence"
        modified_event_id = 4

        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.attendee_user)
            .write({"recurrence_update": "this", "name": new_name})
        )
        self.call_post_commit_hooks()
        self.recurrent_events[modified_event_id].invalidate_recordset()

        self.assertTrue(res)
        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[modified_event_id]),
            {"seriesMasterId": "REC123", "type": "exception", "subject": new_name},
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )
        self.assertEqual(self.recurrent_events[modified_event_id].name, new_name)
        self.assertEqual(
            self.recurrent_events[modified_event_id].follow_recurrence, True
        )

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_one_and_future_events_of_recurrence_from_odoo(
        self, mock_patch, mock_insert, mock_delete
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_name = "my specific event in recurrence"
        modified_event_id = 4

        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.organizer_user)
            .write(
                {
                    "recurrence_update": "subsequent",
                    "name": new_name,
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events.invalidate_recordset()

        self.assertTrue(res)
        self.assertEqual(
            mock_patch.call_count, self.recurrent_events_count - modified_event_id
        )
        for i in range(modified_event_id, self.recurrent_events_count):
            mock_patch.assert_any_call(
                self.held_id(self.recurrent_events[i]),
                {"seriesMasterId": "REC123", "type": "exception", "subject": new_name},
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )
        for i in range(modified_event_id, self.recurrent_events_count):
            self.assertEqual(self.recurrent_events[i].name, new_name)
            self.assertEqual(self.recurrent_events[i].follow_recurrence, True)

        for i in range(modified_event_id):
            self.assertNotEqual(self.recurrent_events[i].name, new_name)

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_start_of_one_and_future_events_of_recurrence_from_odoo(
        self, mock_patch, mock_insert, mock_delete
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return

        new_date = datetime(2021, 9, 29, 10, 0, 0)
        modified_event_id = 4
        existing_recurrences = self.env["calendar.recurrence"].search([])

        expected_deleted_event_ids = [
            self.held_id(r)
            for i, r in enumerate(self.recurrent_events)
            if i in range(modified_event_id + 1, self.recurrent_events_count)
        ]

        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.organizer_user)
            .write(
                {
                    "recurrence_update": "subsequent",
                    "start": new_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events.invalidate_recordset()

        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids),
            self.recurrent_events_count - modified_event_id,
        )

        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[modified_event_id]),
            {
                "seriesMasterId": "REC123",
                "type": "exception",
                "start": {
                    "dateTime": new_date.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                },
                "end": {
                    "dateTime": (new_date + timedelta(hours=1))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "timeZone": "Europe/London",
                },
                "isAllDay": False,
            },
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_start_of_one_and_future_events_of_recurrence_from_odoo_with_overlap(
        self, mock_patch, mock_insert, mock_delete
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_date = datetime(2021, 9, 27, 10, 0, 0)
        modified_event_id = 4
        existing_recurrences = self.env["calendar.recurrence"].search([])

        expected_deleted_event_ids = [
            self.held_id(r)
            for i, r in enumerate(self.recurrent_events)
            if i in range(modified_event_id + 1, self.recurrent_events_count)
        ]

        expected_deleted_event_ids += [
            self.held_id(self.recurrent_events[modified_event_id - 1])
        ]

        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.organizer_user)
            .write(
                {
                    "recurrence_update": "subsequent",
                    "start": new_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events.invalidate_recordset()

        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids),
            self.recurrent_events_count - modified_event_id + 1,
        )

        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[modified_event_id]),
            {
                "seriesMasterId": "REC123",
                "type": "exception",
                "start": {
                    "dateTime": new_date.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                },
                "end": {
                    "dateTime": (new_date + timedelta(hours=1))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "timeZone": "Europe/London",
                },
                "isAllDay": False,
            },
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_one_and_future_events_of_recurrence_from_odoo_attendee_calendar(
        self, mock_patch, mock_insert, mock_delete
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_date = datetime(2021, 9, 29, 10, 0, 0)
        modified_event_id = 4
        existing_recurrences = self.env["calendar.recurrence"].search([])

        expected_deleted_event_ids = [
            self.held_id(r)
            for i, r in enumerate(self.recurrent_events)
            if i in range(modified_event_id + 1, self.recurrent_events_count)
        ]

        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.attendee_user)
            .write(
                {
                    "recurrence_update": "subsequent",
                    "start": new_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events.invalidate_recordset()

        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids),
            self.recurrent_events_count - modified_event_id,
        )

        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[modified_event_id]),
            {
                "seriesMasterId": "REC123",
                "type": "exception",
                "start": {
                    "dateTime": new_date.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                },
                "end": {
                    "dateTime": (new_date + timedelta(hours=1))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "timeZone": "Europe/London",
                },
                "isAllDay": False,
            },
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_all_events_of_recurrence_from_odoo(
        self, mock_patch, mock_insert, mock_delete
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_name = "my specific event in recurrence"

        res = (
            self.recurrent_events[0]
            .with_user(self.organizer_user)
            .write(
                {
                    "recurrence_update": "all",
                    "name": new_name,
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events.invalidate_recordset()

        self.assertTrue(res)
        self.assertEqual(mock_patch.call_count, self.recurrent_events_count)
        for i in range(self.recurrent_events_count):
            mock_patch.assert_any_call(
                self.held_id(self.recurrent_events[i]),
                {"seriesMasterId": "REC123", "type": "exception", "subject": new_name},
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )
            self.assertEqual(self.recurrent_events[i].name, new_name)
            self.assertEqual(self.recurrent_events[i].follow_recurrence, True)

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_start_of_all_events_of_recurrence_from_odoo(
        self, mock_patch, mock_insert, mock_delete
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_date = datetime(2021, 9, 25, 10, 0, 0)
        existing_recurrences = self.env["calendar.recurrence"].search([])
        expected_deleted_event_ids = [
            self.held_id(r)
            for i, r in enumerate(self.recurrent_events)
            if i in range(1, self.recurrent_events_count)
        ]

        res = (
            self.recurrent_events[0]
            .with_user(self.organizer_user)
            .write(
                {
                    "recurrence_update": "all",
                    "start": new_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events.invalidate_recordset()

        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids), self.recurrent_events_count
        )

        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[0]),
            {
                "seriesMasterId": "REC123",
                "type": "exception",
                "start": {
                    "dateTime": new_date.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                },
                "end": {
                    "dateTime": (new_date + timedelta(hours=1))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "timeZone": "Europe/London",
                },
                "isAllDay": False,
            },
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )

        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_all_events_of_recurrence_from_odoo_attendee_calendar(
        self, mock_patch, mock_insert, mock_delete
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        new_date = datetime(2021, 9, 25, 10, 0, 0)
        existing_recurrences = self.env["calendar.recurrence"].search([])
        expected_deleted_event_ids = [
            self.held_id(r)
            for i, r in enumerate(self.recurrent_events)
            if i in range(1, self.recurrent_events_count)
        ]

        res = (
            self.recurrent_events[0]
            .with_user(self.attendee_user)
            .write(
                {
                    "recurrence_update": "all",
                    "start": new_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        )
        self.call_post_commit_hooks()
        self.recurrent_events.invalidate_recordset()

        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids), self.recurrent_events_count
        )

        mock_patch.assert_called_once_with(
            self.held_id(self.recurrent_events[0]),
            {
                "seriesMasterId": "REC123",
                "type": "exception",
                "start": {
                    "dateTime": new_date.replace(tzinfo=UTC).isoformat(),
                    "timeZone": "Europe/London",
                },
                "end": {
                    "dateTime": (new_date + timedelta(hours=1))
                    .replace(tzinfo=UTC)
                    .isoformat(),
                    "timeZone": "Europe/London",
                },
                "isAllDay": False,
            },
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )

        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_simple_event_from_outlook_organizer_calendar(self, mock_get_events):

        new_name = "update simple event"
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        self.simple_event_from_outlook_organizer,
                        subject=new_name,
                        type="exception",
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

        self.assertEqual(self.simple_event.name, new_name)
        self.assertEqual(self.simple_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_an_attendee_spelled_differently_in_outlook_is_the_same_attendee(
        self, mock_get_events
    ):
        attendee = self.simple_event.attendee_ids.filtered(
            lambda a: a.partner_id == self.attendee_user.partner_id
        )
        outlook_attendees = [
            dict(
                outlook_attendee,
                emailAddress={
                    **outlook_attendee["emailAddress"],
                    "address": outlook_attendee["emailAddress"]["address"].title(),
                },
                status={"response": "accepted", "time": "0001-01-01T00:00:00Z"},
            )
            for outlook_attendee in self.simple_event_from_outlook_organizer[
                "attendees"
            ]
        ]
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        self.simple_event_from_outlook_organizer,
                        attendees=outlook_attendees,
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

        self.assertIn(attendee, self.simple_event.attendee_ids)
        self.assertEqual(attendee.state, "accepted")

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_simple_event_from_outlook_attendee_calendar(self, mock_get_events):

        new_name = "update simple event"
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        dict(self.simple_event_from_outlook_organizer, id="789"),
                        subject=new_name,
                        type="exception",
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

        self.assertEqual(self.simple_event.name, new_name)
        self.assertEqual(self.simple_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_name_of_one_event_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):

        new_name = "another event name"
        from_event_index = 2
        events = self.recurrent_event_from_outlook_organizer
        events[from_event_index] = dict(
            events[from_event_index],
            subject=new_name,
            type="exception",
            lastModifiedDateTime=_modified_date_in_the_future(self.simple_event),
        )
        ms_event_id = events[from_event_index]["id"]
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_event = self.find_microsoft("calendar.event", "=", ms_event_id)
        self.assertEqual(updated_event.name, new_name)
        self.assertEqual(updated_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_one_event_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):

        new_date = datetime(2021, 9, 25, 10, 0, 0)
        from_event_index = 3
        events = self.recurrent_event_from_outlook_organizer
        events[from_event_index] = dict(
            events[from_event_index],
            start={
                "dateTime": new_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC",
            },
            type="exception",
            lastModifiedDateTime=_modified_date_in_the_future(
                self.recurrent_base_event
            ),
        )
        ms_event_id = events[from_event_index]["id"]
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_event = self.find_microsoft("calendar.event", "=", ms_event_id)
        self.assertEqual(updated_event.start, new_date)
        self.assertEqual(updated_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_one_event_of_recurrence_from_outlook_organizer_calendar_with_overlap(
        self, mock_get_events
    ):

        new_date = datetime(2021, 9, 23, 10, 0, 0)
        from_event_index = 3
        events = self.recurrent_event_from_outlook_organizer
        events[from_event_index] = dict(
            events[from_event_index],
            start={
                "dateTime": new_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC",
            },
            type="exception",
            lastModifiedDateTime=_modified_date_in_the_future(
                self.recurrent_base_event
            ),
        )
        ms_event_id = events[from_event_index]["id"]
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_event = self.find_microsoft("calendar.event", "=", ms_event_id)
        self.assertEqual(updated_event.start, new_date)
        self.assertEqual(updated_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_name_of_one_event_and_future_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):

        new_name = "another event name"
        from_event_index = 3
        events = self.recurrent_event_from_outlook_organizer
        for i in range(from_event_index, len(events)):
            events[i] = dict(
                events[i],
                subject=f"{new_name}_{i}",
                type="exception",
                lastModifiedDateTime=_modified_date_in_the_future(
                    self.recurrent_base_event
                ),
            )
        ms_event_ids = {
            events[i]["id"]: events[i]["subject"]
            for i in range(from_event_index, len(events))
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_events = self.find_microsoft(
            "calendar.event", "in", tuple(ms_event_ids.keys())
        )
        for e in updated_events:
            self.assertEqual(e.name, ms_event_ids[self.held_id(e)])

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_one_event_and_future_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):

        existing_events = self.env["calendar.event"].search([])
        existing_recurrences = self.env["calendar.recurrence"].search([])

        from_event_index = 3

        old_recurrence_event_count = from_event_index - 1
        new_recurrence_event_count = (
            len(self.recurrent_event_from_outlook_organizer) - from_event_index
        )

        new_rec_first_event_start_date = self.start_date + timedelta(
            days=self.recurrent_event_interval * old_recurrence_event_count - 1
        )
        new_rec_first_event_end_date = new_rec_first_event_start_date + timedelta(
            hours=1
        )
        new_rec_end_date = new_rec_first_event_end_date + timedelta(
            days=self.recurrent_event_interval * new_recurrence_event_count - 1
        )

        events = self.recurrent_event_from_outlook_organizer[0:from_event_index]
        events[0]["lastModifiedDateTime"] = _modified_date_in_the_future(
            self.recurrent_base_event
        )
        events[0]["recurrence"]["range"]["endDate"] = (
            self.recurrence_end_date
            - timedelta(days=self.recurrent_event_interval * new_recurrence_event_count)
        ).strftime("%Y-%m-%d")

        events += [
            dict(
                self.recurrent_event_from_outlook_organizer[0],
                start={
                    "dateTime": new_rec_first_event_start_date.strftime(
                        "%Y-%m-%dT%H:%M:%S.0000000"
                    ),
                    "timeZone": "UTC",
                },
                end={
                    "dateTime": new_rec_first_event_end_date.strftime(
                        "%Y-%m-%dT%H:%M:%S.0000000"
                    ),
                    "timeZone": "UTC",
                },
                id="REC123_new",
                iCalUId="REC456_new",
                recurrence=dict(
                    self.recurrent_event_from_outlook_organizer[0]["recurrence"],
                    range={
                        "startDate": new_rec_first_event_start_date.strftime(
                            "%Y-%m-%d"
                        ),
                        "endDate": new_rec_end_date.strftime("%Y-%m-%d"),
                        "numberOfOccurrences": 0,
                        "recurrenceTimeZone": "Romance Standard Time",
                        "type": "endDate",
                    },
                ),
            )
        ]
        events += [
            dict(
                self.recurrent_event_from_outlook_organizer[1],
                start={
                    "dateTime": (
                        new_rec_first_event_start_date
                        + timedelta(days=i * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                end={
                    "dateTime": (
                        new_rec_first_event_end_date
                        + timedelta(days=i * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                id=f"REC123_new_{i + 1}",
                iCalUId=f"REC456_new_{i + 1}",
                seriesMasterId="REC123_new",
            )
            for i in range(new_recurrence_event_count)
        ]
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        new_events = self.env["calendar.event"].search([]) - existing_events
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertEqual(len(self.recurrence.calendar_event_ids), 2)
        self.assertEqual(
            self.recurrence.repeat_until,
            self.recurrence_end_date.date()
            - timedelta(
                days=self.recurrent_event_interval * new_recurrence_event_count
            ),
        )

        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(len(new_events), new_recurrence_event_count)
        self.assertEqual(self.held_id(new_recurrences), "REC123_new")
        self.assertEqual(self.held_id(new_recurrences, "universal_id"), "REC456_new")

        for i, e in enumerate(sorted(new_events, key=lambda e: e.id)):
            self.assert_odoo_event(
                e,
                {
                    "start": new_rec_first_event_start_date
                    + timedelta(days=i * self.recurrent_event_interval),
                    "stop": new_rec_first_event_end_date
                    + timedelta(days=i * self.recurrent_event_interval),
                    "microsoft_id": f"REC123_new_{i + 1}",
                    "ms_universal_event_id": f"REC456_new_{i + 1}",
                    "recurrence_id": new_recurrences,
                    "follow_recurrence": True,
                },
            )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_one_event_and_future_of_recurrence_from_outlook_organizer_calendar_with_overlap(
        self, mock_get_events
    ):

        existing_events = self.env["calendar.event"].search([])
        existing_recurrences = self.env["calendar.recurrence"].search([])

        from_event_index = 3

        old_recurrence_event_count = from_event_index - 1
        new_recurrence_event_count = (
            len(self.recurrent_event_from_outlook_organizer) - from_event_index
        )

        new_rec_first_event_start_date = self.start_date + timedelta(
            days=self.recurrent_event_interval * (old_recurrence_event_count - 1) - 1
        )
        new_rec_first_event_end_date = new_rec_first_event_start_date + timedelta(
            hours=1
        )
        new_rec_end_date = new_rec_first_event_end_date + timedelta(
            days=self.recurrent_event_interval * (new_recurrence_event_count - 1) - 1
        )

        events = self.recurrent_event_from_outlook_organizer[0:from_event_index]
        events[0]["lastModifiedDateTime"] = _modified_date_in_the_future(
            self.recurrent_base_event
        )
        events[0]["recurrence"]["range"]["endDate"] = (
            self.recurrence_end_date
            - timedelta(days=self.recurrent_event_interval * new_recurrence_event_count)
        ).strftime("%Y-%m-%d")

        events += [
            dict(
                self.recurrent_event_from_outlook_organizer[0],
                start={
                    "dateTime": new_rec_first_event_start_date.strftime(
                        "%Y-%m-%dT%H:%M:%S.0000000"
                    ),
                    "timeZone": "UTC",
                },
                end={
                    "dateTime": new_rec_first_event_end_date.strftime(
                        "%Y-%m-%dT%H:%M:%S.0000000"
                    ),
                    "timeZone": "UTC",
                },
                id="REC123_new",
                iCalUId="REC456_new",
                recurrence=dict(
                    self.recurrent_event_from_outlook_organizer[0]["recurrence"],
                    range={
                        "startDate": new_rec_first_event_start_date.strftime(
                            "%Y-%m-%d"
                        ),
                        "endDate": new_rec_end_date.strftime("%Y-%m-%d"),
                        "numberOfOccurrences": 0,
                        "recurrenceTimeZone": "Romance Standard Time",
                        "type": "endDate",
                    },
                ),
            )
        ]
        events += [
            dict(
                self.recurrent_event_from_outlook_organizer[1],
                start={
                    "dateTime": (
                        new_rec_first_event_start_date
                        + timedelta(days=i * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                end={
                    "dateTime": (
                        new_rec_first_event_end_date
                        + timedelta(days=i * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                id=f"REC123_new_{i + 1}",
                iCalUId=f"REC456_new_{i + 1}",
                seriesMasterId="REC123_new",
            )
            for i in range(new_recurrence_event_count)
        ]
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        new_events = self.env["calendar.event"].search([]) - existing_events
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertEqual(len(self.recurrence.calendar_event_ids), 2)
        self.assertEqual(
            self.recurrence.repeat_until,
            self.recurrence_end_date.date()
            - timedelta(
                days=self.recurrent_event_interval * new_recurrence_event_count
            ),
        )

        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(len(new_events), new_recurrence_event_count)
        self.assertEqual(self.held_id(new_recurrences), "REC123_new")
        self.assertEqual(self.held_id(new_recurrences, "universal_id"), "REC456_new")

        for i, e in enumerate(sorted(new_events, key=lambda e: e.id)):
            self.assert_odoo_event(
                e,
                {
                    "start": new_rec_first_event_start_date
                    + timedelta(days=i * self.recurrent_event_interval),
                    "stop": new_rec_first_event_end_date
                    + timedelta(days=i * self.recurrent_event_interval),
                    "microsoft_id": f"REC123_new_{i + 1}",
                    "ms_universal_event_id": f"REC456_new_{i + 1}",
                    "recurrence_id": new_recurrences,
                    "follow_recurrence": True,
                },
            )

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_name_of_all_events_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):

        new_name = "another event name"
        events = self.recurrent_event_from_outlook_organizer
        for i, e in enumerate(events):
            events[i] = dict(
                e,
                subject=f"{new_name}_{i}",
                lastModifiedDateTime=_modified_date_in_the_future(
                    self.recurrent_base_event
                ),
            )
        ms_events_to_update = {
            events[i]["id"]: events[i]["subject"] for i in range(1, len(events))
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_events = self.find_microsoft(
            "calendar.event", "in", tuple(ms_events_to_update.keys())
        )
        for e in updated_events:
            self.assertEqual(e.name, ms_events_to_update[self.held_id(e)])
            self.assertEqual(e.follow_recurrence, True)

    def _prepare_outlook_events_for_all_events_start_date_update(self, nb_of_events):
        new_start_date = datetime(2021, 9, 21, 10, 0, 0)
        new_end_date = new_start_date + timedelta(hours=1)

        events = [
            dict(
                self.recurrent_event_from_outlook_organizer[0],
                start={
                    "dateTime": new_start_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                end={
                    "dateTime": new_end_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                recurrence=dict(
                    self.recurrent_event_from_outlook_organizer[0]["recurrence"],
                    range={
                        "startDate": new_start_date.strftime("%Y-%m-%d"),
                        "endDate": (
                            new_end_date
                            + timedelta(
                                days=self.recurrent_event_interval * nb_of_events
                            )
                        ).strftime("%Y-%m-%d"),
                        "numberOfOccurrences": 0,
                        "recurrenceTimeZone": "Romance Standard Time",
                        "type": "endDate",
                    },
                ),
                lastModifiedDateTime=_modified_date_in_the_future(
                    self.recurrent_base_event
                ),
            )
        ]

        events += nb_of_events * [self.recurrent_event_from_outlook_organizer[1]]
        for i in range(1, nb_of_events + 1):
            events[i] = dict(
                events[i],
                id=f"REC123_EVENT_{i}",
                iCalUId=f"REC456_EVENT_{i}",
                start={
                    "dateTime": (
                        new_start_date
                        + timedelta(days=(i - 1) * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                end={
                    "dateTime": (
                        new_end_date
                        + timedelta(days=(i - 1) * self.recurrent_event_interval)
                    ).strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                    "timeZone": "UTC",
                },
                lastModifiedDateTime=_modified_date_in_the_future(
                    self.recurrent_base_event
                ),
            )

        return events

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_all_events_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):

        events = self._prepare_outlook_events_for_all_events_start_date_update(
            self.recurrent_events_count
        )
        ms_events_to_update = {
            events[i]["id"]: events[i]["start"]
            for i in range(1, self.recurrent_events_count + 1)
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_events = self.find_microsoft(
            "calendar.event", "in", tuple(ms_events_to_update.keys())
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[self.held_id(e)]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_all_events_of_recurrence_with_more_events(
        self, mock_get_events
    ):

        nb_of_events = self.recurrent_events_count + 2
        events = self._prepare_outlook_events_for_all_events_start_date_update(
            nb_of_events
        )
        ms_events_to_update = {
            events[i]["id"]: events[i]["start"] for i in range(1, nb_of_events + 1)
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_events = self.find_microsoft(
            "calendar.event", "in", tuple(ms_events_to_update.keys())
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[self.held_id(e)]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_all_events_of_recurrence_with_less_events(
        self, mock_get_events
    ):

        nb_of_events = self.recurrent_events_count - 2
        events = self._prepare_outlook_events_for_all_events_start_date_update(
            nb_of_events
        )
        ms_events_to_update = {
            events[i]["id"]: events[i]["start"] for i in range(1, nb_of_events + 1)
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_events = self.find_microsoft(
            "calendar.event", "in", tuple(ms_events_to_update.keys())
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[self.held_id(e)]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_all_events_of_recurrence_with_exceptions(
        self, mock_get_events
    ):

        nb_of_events = self.recurrent_events_count - 2
        events = self._prepare_outlook_events_for_all_events_start_date_update(
            nb_of_events
        )

        new_start_date = parse(events[2]["start"]["dateTime"]) + timedelta(days=1)
        new_end_date = parse(events[2]["end"]["dateTime"]) + timedelta(days=1)
        events[2] = dict(
            events[2],
            start={
                "dateTime": new_start_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC",
            },
            end={
                "dateTime": new_end_date.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                "timeZone": "UTC",
            },
            type="exception",
        )
        ms_events_to_update = {
            events[i]["id"]: events[i]["start"] for i in range(1, nb_of_events + 1)
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        updated_events = self.find_microsoft(
            "calendar.event", "in", tuple(ms_events_to_update.keys())
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[self.held_id(e)]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "patch")
    def test_forbid_simple_event_become_recurrence_sync_on(self, mock_patch):

        self.assertFalse(self.env.user._calendar_sync_account("microsoft").stopped)

        simple_event = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        with self.assertRaises(UserError):
            simple_event.write(
                {
                    "recurrency": True,
                    "repeat_unit": "week",
                    "event_tz": "America/Sao_Paulo",
                    "repeat_type": "count",
                    "repeat_interval": 1,
                    "repeat_number": 1,
                    "fri": True,
                    "month_by": "date",
                    "day": 1,
                    "weekday": "FRI",
                    "byday": "2",
                }
            )

        mock_patch.assert_not_called()

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_synced_event_with_sync_config_paused(self, mock_patch):
        self.organizer_user._calendar_sync_account("microsoft").stopped = False
        self.env["calendar.sync.account"]._set_paused("microsoft", True)

        self.simple_event.with_user(self.organizer_user).write(
            {"name": "updated simple event"}
        )
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertFalse(
            self.organizer_user._calendar_sync_account("microsoft").stopped
        )
        self.assertEqual(
            self.organizer_user._calendar_sync_status("microsoft"), "sync_paused"
        )
        self.assertTrue(
            self.awaits_push(self.simple_event),
            "The event waits for the synchronization to resume",
        )
        mock_patch.assert_not_called()

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_changing_event_organizer_to_another_user(
        self, mock_insert, mock_delete, mock_get_events
    ):
        self.assertTrue(
            self.env["calendar.event"]
            .with_user(self.attendee_user)
            ._check_microsoft_sync_status()
        )
        self.simple_event_values["user_id"] = self.organizer_user.id
        self.simple_event_values["partner_ids"] = [
            Command.set([self.organizer_user.partner_id.id])
        ]
        event = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        self.link_microsoft(
            event, self.organizer_user, "test_id_for_organizer", "test_id_for_event"
        )

        self.attendee_user._calendar_sync_account("microsoft").stopped = True
        with self.assertRaises(ValidationError):
            event.with_user(self.organizer_user).write(
                {"user_id": self.attendee_user.id}
            )

        self.attendee_user._calendar_sync_account("microsoft").stopped = False
        with self.assertRaises(ValidationError):
            event.with_user(self.organizer_user).write(
                {"user_id": self.attendee_user.id}
            )

        event_id = "recreated"
        event_iCalUId = "recreated_uid"
        mock_insert.return_value = {"id": event_id, "iCalUId": event_iCalUId}
        mock_get_events.return_value = ([], None)

        event.with_user(self.organizer_user).write(
            {
                "user_id": self.attendee_user.id,
                "partner_ids": [
                    Command.set(
                        [
                            self.organizer_user.partner_id.id,
                            self.attendee_user.partner_id.id,
                        ]
                    )
                ],
            }
        )
        new_event = self.env["calendar.event"].search([("id", ">", event.id)])
        self.call_post_commit_hooks()
        new_event.invalidate_recordset()

        mock_delete.assert_any_call(
            "test_id_for_organizer",
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )
        self.assertEqual(
            len(new_event),
            1,
            "A single event should be created after updating the organizer.",
        )
        self.assertEqual(
            new_event.user_id,
            self.attendee_user,
            "The event organizer must be user B (self.attendee_user) after the event organizer update.",
        )
        self.assertTrue(
            self.attendee_user.partner_id.id in new_event.partner_ids.ids,
            "User B (self.attendee_user) should be listed as attendee after the event organizer update.",
        )

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_restart_sync_with_synced_recurrence(self, mock_patch):
        self.organizer_user.calendar_sync_stop("microsoft")
        self.recurrent_events._microsoft_forget()
        self.recurrent_events.with_user(self.organizer_user).write(
            {"follow_recurrence": False}
        )
        self.attendee_user.with_user(self.attendee_user).calendar_sync_restart(
            "microsoft"
        )
        self.organizer_user.with_user(self.organizer_user).calendar_sync_restart(
            "microsoft"
        )
        self.assertTrue(all(self.awaits_push(ev) for ev in self.recurrent_events))

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_old_event_synced_with_outlook(self, mock_get_events):
        self.microsoft_link(self.simple_event, self.organizer_user).remote_etag = "CK1"
        name = self.simple_event.name
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        self.simple_event_from_outlook_organizer,
                        subject="a copy Odoo has already applied",
                        changeKey="CK1",
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
        self.assertEqual(self.simple_event.name, name)
