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

    # -------------------------------------------------------------------------------
    # Update from Odoo to Outlook
    # -------------------------------------------------------------------------------

    # ------ Simple event ------

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_odoo_simple_event_without_sync(self, mock_patch):
        """
        Update an Odoo event without Outlook sync enabled
        """

        # arrange
        self.organizer_user._calendar_sync_account("microsoft").stopped = True

        # act
        self.simple_event.write({"name": "my new simple event"})
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        # assert
        mock_patch.assert_not_called()

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_simple_event_with_sync_config_paused(self, mock_patch):
        """An edit made while the sync is paused waits for the unpause.

        `write` marked the record only while the status was `sync_active`, so
        a paused edit was neither sent nor marked, and the resumed sync never
        picked it up.
        """
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
        """Outlook gives the attendee's copy an id of its own: reading it in the
        attendee's synchronization took that id for the event's, and the
        organizer's next patch went to an item their calendar does not have."""
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
        mock_patch.return_value = True
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
        """
        Update an Odoo event with Outlook sync enabled
        """

        # arrange
        mock_patch.return_value = True

        # act
        res = self.simple_event.with_user(self.organizer_user).write(
            {"name": "my new simple event"}
        )
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        # assert
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
        """A run stamps its date at its end: stamped at its start, the run kept
        only what was written in the five minutes before it, and an edit whose
        immediate push was lost stayed pending for good."""
        mock_get_events.return_value = (MicrosoftEvent([]), "next-token")
        mock_patch.return_value = True
        account = self.organizer_user._calendar_sync_account("microsoft")
        account.write(
            {"sync_token": "a-token", "last_sync_date": datetime(2021, 9, 22, 9, 0)}
        )
        with self.mock_datetime_and_now("2021-09-22 10:00:00"):
            self.simple_event.with_user(self.organizer_user).write(
                {"name": "edited while Outlook was down"}
            )
        # the push the write queued never reached Outlook
        self.env.cr.postcommit.clear()
        self.assertTrue(self.awaits_push(self.simple_event))

        with self.mock_datetime_and_now("2021-09-22 11:00:00"):
            self.organizer_user.with_user(
                self.organizer_user
            ).sudo()._calendar_sync_run("microsoft")
            self.call_post_commit_hooks()

        mock_patch.assert_called_once_with(
            self.simple_event.microsoft_id,
            ANY,
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )
        self.assertEqual(
            mock_patch.call_args.args[1]["subject"], "edited while Outlook was down"
        )

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_simple_event_from_odoo_attendee_calendar(self, mock_patch):
        """
        Update an Odoo event from the attendee calendar.
        """

        # arrange
        mock_patch.return_value = True

        # act
        res = self.simple_event.with_user(self.attendee_user).write(
            {"name": "my new simple event"}
        )
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        # assert
        self.assertTrue(res)
        self.assert_patched(
            mock_patch,
            "123",
            {"subject": "my new simple event", "isOnlineMeeting": None},
            self.organizer_user,
        )
        self.assertEqual(self.simple_event.name, "my new simple event")

    # ------ One event in a recurrence ------

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_one_event_of_recurrence_from_odoo(self, mock_patch):
        """
        Update one Odoo event name from a recurrence from the organizer calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_name = "my specific event in recurrence"
        modified_event_id = 4

        # act
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

        # assert
        self.assertTrue(res)
        mock_patch.assert_called_once_with(
            self.recurrent_events[modified_event_id].microsoft_id,
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
        """
        Update one Odoo event start date from a recurrence from the organizer calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_date = datetime(2021, 9, 29, 10, 0, 0)
        modified_event_id = 4

        # act
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

        # assert
        self.assertTrue(res)
        mock_patch.assert_called_once_with(
            self.recurrent_events[modified_event_id].microsoft_id,
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
        """
        Update one Odoo event start date from a recurrence from the organizer calendar, in order to
        overlap another existing event.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_date = datetime(2021, 9, 27, 10, 0, 0)
        modified_event_id = 4

        # act
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

        # assert
        mock_patch.assert_not_called()

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_one_event_of_recurrence_from_odoo_attendee_calendar(
        self, mock_patch
    ):
        """
        Update one Odoo event name from a recurrence from the atendee calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_name = "my specific event in recurrence"
        modified_event_id = 4

        # act
        res = (
            self.recurrent_events[modified_event_id]
            .with_user(self.attendee_user)
            .write({"recurrence_update": "this", "name": new_name})
        )
        self.call_post_commit_hooks()
        self.recurrent_events[modified_event_id].invalidate_recordset()

        # assert
        self.assertTrue(res)
        mock_patch.assert_called_once_with(
            self.recurrent_events[modified_event_id].microsoft_id,
            {"seriesMasterId": "REC123", "type": "exception", "subject": new_name},
            connection=mock_get_connection(self.organizer_user),
            timeout=ANY,
        )
        self.assertEqual(self.recurrent_events[modified_event_id].name, new_name)
        self.assertEqual(
            self.recurrent_events[modified_event_id].follow_recurrence, True
        )

    # ------ One and future events in a recurrence ------

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_one_and_future_events_of_recurrence_from_odoo(
        self, mock_patch, mock_insert, mock_delete
    ):
        """
        Update a Odoo event name and future events from a recurrence from the organizer calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_name = "my specific event in recurrence"
        modified_event_id = 4

        # act
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

        # assert
        self.assertTrue(res)
        self.assertEqual(
            mock_patch.call_count, self.recurrent_events_count - modified_event_id
        )
        for i in range(modified_event_id, self.recurrent_events_count):
            mock_patch.assert_any_call(
                self.recurrent_events[i].microsoft_id,
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
        """
        Update a Odoo event start date and future events from a recurrence from the organizer calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # When a time-related field is changed, the event does not follow the recurrence scheme anymore.
        # With Outlook, another constraint is that the new start of the event cannot overlap/cross the start
        # date of another event of the recurrence (see calendar_microsoft/models/calendar.py
        # _check_recurrence_overlapping() for more explanation)
        #
        # In this case, as we also update future events, the recurrence should be splitted into 2 parts:
        #  - the original recurrence should end just before the first updated event
        #  - a second recurrence should start at the first updated event

        # arrange
        new_date = datetime(2021, 9, 29, 10, 0, 0)
        modified_event_id = 4
        existing_recurrences = self.env["calendar.recurrence"].search([])

        expected_deleted_event_ids = [
            r.microsoft_id
            for i, r in enumerate(self.recurrent_events)
            if i in range(modified_event_id + 1, self.recurrent_events_count)
        ]

        # act
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

        # assert
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        # a new recurrence should be created from the modified event to the end
        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids),
            self.recurrent_events_count - modified_event_id,
        )

        # future events of the old recurrence should have been removed
        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

        # the base event should have been modified
        mock_patch.assert_called_once_with(
            self.recurrent_events[modified_event_id].microsoft_id,
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
        """
        Update a Odoo event start date and future events from a recurrence from the organizer calendar,
        overlapping an existing event.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_date = datetime(2021, 9, 27, 10, 0, 0)
        modified_event_id = 4
        existing_recurrences = self.env["calendar.recurrence"].search([])

        expected_deleted_event_ids = [
            r.microsoft_id
            for i, r in enumerate(self.recurrent_events)
            if i in range(modified_event_id + 1, self.recurrent_events_count)
        ]

        # as the test overlap the previous event of the updated event, this previous event
        # should be removed too
        expected_deleted_event_ids += [
            self.recurrent_events[modified_event_id - 1].microsoft_id
        ]

        # act
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

        # assert
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        # a new recurrence should be created from the modified event to the end
        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids),
            self.recurrent_events_count - modified_event_id + 1,
        )

        # future events of the old recurrence should have been removed + the overlapped event
        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

        # the base event should have been modified
        mock_patch.assert_called_once_with(
            self.recurrent_events[modified_event_id].microsoft_id,
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
        """
        Update a Odoo event name and future events from a recurrence from the attendee calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_date = datetime(2021, 9, 29, 10, 0, 0)
        modified_event_id = 4
        existing_recurrences = self.env["calendar.recurrence"].search([])

        expected_deleted_event_ids = [
            r.microsoft_id
            for i, r in enumerate(self.recurrent_events)
            if i in range(modified_event_id + 1, self.recurrent_events_count)
        ]

        # act
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

        # assert
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        self.assertTrue(res)

        # a new recurrence should be created from the modified event to the end
        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(new_recurrences.base_event_id.start, new_date)
        self.assertEqual(
            len(new_recurrences.calendar_event_ids),
            self.recurrent_events_count - modified_event_id,
        )

        # future events of the old recurrence should have been removed
        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

        # the base event should have been modified
        mock_patch.assert_called_once_with(
            self.recurrent_events[modified_event_id].microsoft_id,
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

    # ------ All events in a recurrence ------

    @patch.object(MicrosoftCalendarService, "delete")
    @patch.object(MicrosoftCalendarService, "insert")
    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_name_of_all_events_of_recurrence_from_odoo(
        self, mock_patch, mock_insert, mock_delete
    ):
        """
        Update all events name from a recurrence from the organizer calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_name = "my specific event in recurrence"

        # act
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

        # assert
        self.assertTrue(res)
        self.assertEqual(mock_patch.call_count, self.recurrent_events_count)
        for i in range(self.recurrent_events_count):
            mock_patch.assert_any_call(
                self.recurrent_events[i].microsoft_id,
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
        """
        Update all events start date from a recurrence from the organizer calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_date = datetime(2021, 9, 25, 10, 0, 0)
        existing_recurrences = self.env["calendar.recurrence"].search([])
        expected_deleted_event_ids = [
            r.microsoft_id
            for i, r in enumerate(self.recurrent_events)
            if i in range(1, self.recurrent_events_count)
        ]

        # act
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

        # assert
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
            self.recurrent_events[0].microsoft_id,
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

        # events (except the base one) of the old recurrence should have been removed
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
        """
        Update all events start date from a recurrence from the attendee calendar.
        """
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        # arrange
        new_date = datetime(2021, 9, 25, 10, 0, 0)
        existing_recurrences = self.env["calendar.recurrence"].search([])
        expected_deleted_event_ids = [
            r.microsoft_id
            for i, r in enumerate(self.recurrent_events)
            if i in range(1, self.recurrent_events_count)
        ]

        # act
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

        # assert
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
            self.recurrent_events[0].microsoft_id,
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

        # events (except the base one) of the old recurrence should have been removed
        for e_id in expected_deleted_event_ids:
            mock_delete.assert_any_call(
                e_id,
                connection=mock_get_connection(self.organizer_user),
                timeout=ANY,
            )

    # -------------------------------------------------------------------------------
    # Update from Outlook to Odoo
    # -------------------------------------------------------------------------------

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_simple_event_from_outlook_organizer_calendar(self, mock_get_events):
        """
        Update a simple event from Outlook organizer calendar.
        """

        # arrange
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

        # act
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # assert
        self.assertEqual(self.simple_event.name, new_name)
        self.assertEqual(self.simple_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_an_attendee_spelled_differently_in_outlook_is_the_same_attendee(
        self, mock_get_events
    ):
        """Outlook may spell an address differently from Odoo; the answer lands
        on the existing attendee. Pinned for the shared engine: Google's two
        paths died on `calendar_attendee_event_id_partner_id_unique` here."""
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
        """
        Update a simple event from Outlook attendee calendar.
        """

        # arrange
        new_name = "update simple event"
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    dict(
                        dict(
                            self.simple_event_from_outlook_organizer, id="789"
                        ),  # same iCalUId but different id
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

        # act
        self.attendee_user.with_user(self.attendee_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # assert
        self.assertEqual(self.simple_event.name, new_name)
        self.assertEqual(self.simple_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_name_of_one_event_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):
        """
        Update one event name from a recurrence from Outlook organizer calendar.
        """

        # arrange
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

        # act
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # assert
        updated_event = self.env["calendar.event"].search(
            [("microsoft_id", "=", ms_event_id)]
        )
        self.assertEqual(updated_event.name, new_name)
        self.assertEqual(updated_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_one_event_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):
        """
        Update one event start date from a recurrence from Outlook organizer calendar.
        """

        # arrange
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

        # act
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # assert
        updated_event = self.env["calendar.event"].search(
            [("microsoft_id", "=", ms_event_id)]
        )
        self.assertEqual(updated_event.start, new_date)
        self.assertEqual(updated_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_one_event_of_recurrence_from_outlook_organizer_calendar_with_overlap(
        self, mock_get_events
    ):
        """
        Update one event start date from a recurrence from Outlook organizer calendar, with event overlap.
        """

        # arrange
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

        # act
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # assert
        updated_event = self.env["calendar.event"].search(
            [("microsoft_id", "=", ms_event_id)]
        )
        self.assertEqual(updated_event.start, new_date)
        self.assertEqual(updated_event.follow_recurrence, False)

    @freeze_time("2021-09-22")
    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_name_of_one_event_and_future_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):
        """
        Update one event name and future events from a recurrence from Outlook organizer calendar.
        """

        # arrange
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

        # act
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # assert
        updated_events = self.env["calendar.event"].search(
            [("microsoft_id", "in", tuple(ms_event_ids.keys()))]
        )
        for e in updated_events:
            self.assertEqual(e.name, ms_event_ids[e.microsoft_id])

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_one_event_and_future_of_recurrence_from_outlook_organizer_calendar(
        self, mock_get_events
    ):
        """
        Update one event start date and future events from a recurrence from Outlook organizer calendar.

        When a time field is modified on an event and the future events of the recurrence, the recurrence is splitted:
        - the first one is still the same than the existing one, but stops at the first modified event,
        - the second one containing newly created events but based on the old events which have been deleted.
        """

        # ----------- ARRANGE --------------

        existing_events = self.env["calendar.event"].search([])
        existing_recurrences = self.env["calendar.recurrence"].search([])

        # event index from where the current recurrence will be splitted/modified
        from_event_index = 3

        # number of events in both recurrences
        old_recurrence_event_count = from_event_index - 1
        new_recurrence_event_count = (
            len(self.recurrent_event_from_outlook_organizer) - from_event_index
        )

        # dates for the new recurrences (shift event dates of 1 day in the past)
        new_rec_first_event_start_date = self.start_date + timedelta(
            days=self.recurrent_event_interval * old_recurrence_event_count - 1
        )
        new_rec_first_event_end_date = new_rec_first_event_start_date + timedelta(
            hours=1
        )
        new_rec_end_date = new_rec_first_event_end_date + timedelta(
            days=self.recurrent_event_interval * new_recurrence_event_count - 1
        )

        # prepare first recurrence data in received Outlook events
        events = self.recurrent_event_from_outlook_organizer[0:from_event_index]
        events[0]["lastModifiedDateTime"] = _modified_date_in_the_future(
            self.recurrent_base_event
        )
        events[0]["recurrence"]["range"]["endDate"] = (
            self.recurrence_end_date
            - timedelta(days=self.recurrent_event_interval * new_recurrence_event_count)
        ).strftime("%Y-%m-%d")

        # prepare second recurrence data in received Outlook events
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
        # ... and the recurrent events
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

        # ----------- ACT --------------

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # ----------- ASSERT --------------

        new_events = self.env["calendar.event"].search([]) - existing_events
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        # old recurrence
        self.assertEqual(len(self.recurrence.calendar_event_ids), 2)
        self.assertEqual(
            self.recurrence.repeat_until,
            self.recurrence_end_date.date()
            - timedelta(
                days=self.recurrent_event_interval * new_recurrence_event_count
            ),
        )

        # new recurrence
        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(len(new_events), new_recurrence_event_count)
        self.assertEqual(new_recurrences.microsoft_id, "REC123_new")
        self.assertEqual(new_recurrences.ms_universal_event_id, "REC456_new")

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
        """
        Update one event start date and future events from a recurrence from Outlook organizer calendar,
        overlapping an existing event.
        """

        # ----------- ARRANGE --------------

        existing_events = self.env["calendar.event"].search([])
        existing_recurrences = self.env["calendar.recurrence"].search([])

        # event index from where the current recurrence will be splitted/modified
        from_event_index = 3

        # number of events in both recurrences
        old_recurrence_event_count = from_event_index - 1
        new_recurrence_event_count = (
            len(self.recurrent_event_from_outlook_organizer) - from_event_index
        )

        # dates for the new recurrences (shift event dates of (recurrent_event_interval + 1) days in the past
        # to overlap an event.
        new_rec_first_event_start_date = self.start_date + timedelta(
            days=self.recurrent_event_interval * (old_recurrence_event_count - 1) - 1
        )
        new_rec_first_event_end_date = new_rec_first_event_start_date + timedelta(
            hours=1
        )
        new_rec_end_date = new_rec_first_event_end_date + timedelta(
            days=self.recurrent_event_interval * (new_recurrence_event_count - 1) - 1
        )

        # prepare first recurrence data in received Outlook events
        events = self.recurrent_event_from_outlook_organizer[0:from_event_index]
        events[0]["lastModifiedDateTime"] = _modified_date_in_the_future(
            self.recurrent_base_event
        )
        events[0]["recurrence"]["range"]["endDate"] = (
            self.recurrence_end_date
            - timedelta(days=self.recurrent_event_interval * new_recurrence_event_count)
        ).strftime("%Y-%m-%d")

        # prepare second recurrence data in received Outlook events
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
        # ... and the recurrent events
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

        # ----------- ACT --------------

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # ----------- ASSERT --------------

        new_events = self.env["calendar.event"].search([]) - existing_events
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )

        # old recurrence
        self.assertEqual(len(self.recurrence.calendar_event_ids), 2)
        self.assertEqual(
            self.recurrence.repeat_until,
            self.recurrence_end_date.date()
            - timedelta(
                days=self.recurrent_event_interval * new_recurrence_event_count
            ),
        )

        # new recurrence
        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(len(new_events), new_recurrence_event_count)
        self.assertEqual(new_recurrences.microsoft_id, "REC123_new")
        self.assertEqual(new_recurrences.ms_universal_event_id, "REC456_new")

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
        """
        Update all event names of a recurrence from Outlook organizer calendar.
        """

        # arrange
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

        # act
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # assert
        updated_events = self.env["calendar.event"].search(
            [("microsoft_id", "in", tuple(ms_events_to_update.keys()))]
        )
        for e in updated_events:
            self.assertEqual(e.name, ms_events_to_update[e.microsoft_id])
            self.assertEqual(e.follow_recurrence, True)

    def _prepare_outlook_events_for_all_events_start_date_update(self, nb_of_events):
        """
        Utility method to avoid repeating data preparation for all tests
        about updating the start date of all events of a recurrence
        """
        new_start_date = datetime(2021, 9, 21, 10, 0, 0)
        new_end_date = new_start_date + timedelta(hours=1)

        # prepare recurrence based on self.recurrent_event_from_outlook_organizer[0] which is the Outlook recurrence
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

        # prepare all events based on self.recurrent_event_from_outlook_organizer[1] which is the first Outlook event
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
        """
        Update all event start date of a recurrence from Outlook organizer calendar.
        """

        # ----------- ARRANGE -----------
        events = self._prepare_outlook_events_for_all_events_start_date_update(
            self.recurrent_events_count
        )
        ms_events_to_update = {
            events[i]["id"]: events[i]["start"]
            for i in range(1, self.recurrent_events_count + 1)
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        # ----------- ACT -----------

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # ----------- ASSERT -----------

        updated_events = self.env["calendar.event"].search(
            [("microsoft_id", "in", tuple(ms_events_to_update.keys()))]
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[e.microsoft_id]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_all_events_of_recurrence_with_more_events(
        self, mock_get_events
    ):
        """
        Update all event start date of a recurrence from Outlook organizer calendar, where
        more events have been added (the end date is later in the year)
        """
        # ----------- ARRANGE -----------

        nb_of_events = self.recurrent_events_count + 2
        events = self._prepare_outlook_events_for_all_events_start_date_update(
            nb_of_events
        )
        ms_events_to_update = {
            events[i]["id"]: events[i]["start"] for i in range(1, nb_of_events + 1)
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        # ----------- ACT -----------

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # ----------- ASSERT -----------
        updated_events = self.env["calendar.event"].search(
            [("microsoft_id", "in", tuple(ms_events_to_update.keys()))]
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[e.microsoft_id]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_all_events_of_recurrence_with_less_events(
        self, mock_get_events
    ):
        """
        Update all event start date of a recurrence from Outlook organizer calendar, where
        some events have been removed (the end date is earlier in the year)
        """
        # ----------- ARRANGE -----------

        nb_of_events = self.recurrent_events_count - 2
        events = self._prepare_outlook_events_for_all_events_start_date_update(
            nb_of_events
        )
        ms_events_to_update = {
            events[i]["id"]: events[i]["start"] for i in range(1, nb_of_events + 1)
        }
        mock_get_events.return_value = (MicrosoftEvent(events), None)

        # ----------- ACT -----------

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # ----------- ASSERT -----------

        updated_events = self.env["calendar.event"].search(
            [("microsoft_id", "in", tuple(ms_events_to_update.keys()))]
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[e.microsoft_id]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_update_start_of_all_events_of_recurrence_with_exceptions(
        self, mock_get_events
    ):
        """
        Update all event start date of a recurrence from Outlook organizer calendar, where
        an event does not follow the recurrence anymore (it became an exception)
        """
        # ----------- ARRANGE -----------

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

        # ----------- ACT -----------

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        # ----------- ASSERT -----------

        updated_events = self.env["calendar.event"].search(
            [("microsoft_id", "in", tuple(ms_events_to_update.keys()))]
        )
        for e in updated_events:
            self.assertEqual(
                e.start.strftime("%Y-%m-%dT%H:%M:%S.0000000"),
                ms_events_to_update[e.microsoft_id]["dateTime"],
            )

    @patch.object(MicrosoftCalendarService, "patch")
    def test_forbid_simple_event_become_recurrence_sync_on(self, mock_patch):
        """
        Forbid in Odoo simple event becoming a recurrence when Outlook Calendar sync is active.
        """
        # Set custom calendar token validity to simulate real scenario.

        # Assert that synchronization with Outlook Calendar is active.
        self.assertFalse(self.env.user._calendar_sync_account("microsoft").stopped)

        # Simulate upgrade of a simple event to recurrent event (forbidden).
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

        # Assert that no patch call was made due to the recurrence update forbiddance.
        mock_patch.assert_not_called()

    @patch.object(MicrosoftCalendarService, "patch")
    def test_update_synced_event_with_sync_config_paused(self, mock_patch):
        """
        An event updated while the synchronization is paused waits to be sent
        once it resumes.
        """
        # Set user synchronization configuration as active and pause it.
        self.organizer_user._calendar_sync_account("microsoft").stopped = False
        self.env["calendar.sync.account"]._set_paused("microsoft", True)

        # Try to update a simple event in Odoo Calendar.
        self.simple_event.with_user(self.organizer_user).write(
            {"name": "updated simple event"}
        )
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        # Ensure that synchronization is paused, delete wasn't called and record is waiting to be synced again.
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
        """
        Allow editing the event organizer to another user only if the proposed organizer have its Odoo Calendar synced.
        The current event is deleted and then recreated with the new organizer.
        An event with organizer as user A (self.organizer_user) will have its organizer changed to user B (self.attendee_user).
        """
        # Create event with organizer as user A and only the organizer as attendee.
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
        # Simulate sync where the api update the microsoft_id field
        event.ms_universal_event_id = "test_id_for_event"
        event.microsoft_id = "test_id_for_organizer"

        # Deactivate user B's calendar synchronization. Try changing the event organizer to user B.
        # A ValidationError must be thrown because user B's calendar is not synced.
        self.attendee_user._calendar_sync_account("microsoft").stopped = True
        with self.assertRaises(ValidationError):
            event.with_user(self.organizer_user).write(
                {"user_id": self.attendee_user.id}
            )

        # Activate user B's calendar synchronization and try again without listing user B as an attendee.
        # Another ValidationError must be thrown.
        self.attendee_user._calendar_sync_account("microsoft").stopped = False
        with self.assertRaises(ValidationError):
            event.with_user(self.organizer_user).write(
                {"user_id": self.attendee_user.id}
            )

        # Set mock return values for the event re-creation.
        event_id = "recreated"
        event_iCalUId = "recreated_uid"
        mock_insert.return_value = (event_id, event_iCalUId)
        mock_get_events.return_value = ([], None)

        # Change the event organizer: user B (the organizer) is synced and now listed as an attendee.
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

        # The old copy is deleted from the calendar holding it, the former
        # organizer's; the new organizer's copy is a new event.
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
        """Ensure that sync restart is not blocked when there are recurrence outliers in Odoo database."""
        # Stop synchronization, set recurrent events as outliers and restart sync with Outlook.
        self.organizer_user.calendar_sync_stop("microsoft")
        self.recurrent_events.with_user(self.organizer_user).write(
            {
                "microsoft_id": False,
                "ms_universal_event_id": False,
                "follow_recurrence": False,
            }
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
        """Outlook's change key says whether its item changed since Odoo last
        heard of it: an item listed again unchanged is not applied again, so
        the write it would make mails no one."""
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
