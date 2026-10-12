from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch

import requests

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import tagged

from odoo.addons.calendar_microsoft.tests.common import (
    TestCommon,
    _modified_date_in_the_future,
    distinct_inserts,
    mock_get_connection,
)
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    MicrosoftCalendarService,
)
from odoo.addons.calendar_microsoft.utils.microsoft_event import MicrosoftEvent
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers
from odoo.addons.mail.tests.common import mail_new_test_user


@tagged("post_install", "-at_install")
@patch.object(CalendarSyncUsers, "_calendar_sync_connection", mock_get_connection)
class TestCreateEvents(TestCommon):
    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_simple_event_without_sync(self, mock_insert):

        self.organizer_user._calendar_sync_account("microsoft").stopped = True

        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        self.call_post_commit_hooks()
        record.invalidate_recordset()

        mock_insert.assert_not_called()
        self.assertFalse(self.microsoft_link(record, self.organizer_user))

    @patch.object(
        MicrosoftCalendarService, "get_events", return_value=(MicrosoftEvent(), None)
    )
    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_simple_event_without_email(self, mock_insert, mock_get_events):
        self.attendee_user.partner_id.email = False

        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        self.call_post_commit_hooks()

        mock_insert.assert_not_called()
        link = self.microsoft_link(record, self.organizer_user)
        self.assertIn("email address", link.error)
        self.assertFalse(self.awaits_push(record))
        notes = record.message_ids.filtered(lambda m: "Outlook refused" in m.body)
        self.assertEqual(len(notes), 1)

        self.sync_microsoft(self.organizer_user)
        mock_insert.assert_not_called()
        self.assertEqual(
            len(record.message_ids.filtered(lambda m: "Outlook refused" in m.body)),
            1,
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_create_simple_event_from_outlook_organizer_calendar(self, mock_get_events):

        mock_get_events.return_value = (
            MicrosoftEvent([self.simple_event_from_outlook_organizer]),
            None,
        )
        existing_records = self.env["calendar.event"].search([])

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        records = self.env["calendar.event"].search([])
        new_records = records - existing_records
        self.assertEqual(len(new_records), 1)
        self.assert_odoo_event(new_records, self.expected_odoo_event_from_outlook)
        self.assertEqual(new_records.user_id, self.organizer_user)
        self.assertFalse(self.awaits_push(new_records))

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_create_simple_event_from_outlook_attendee_calendar_and_organizer_exists_in_odoo(
        self, mock_get_events
    ):

        mock_get_events.return_value = (
            MicrosoftEvent([self.simple_event_from_outlook_attendee]),
            None,
        )
        existing_records = self.env["calendar.event"].search([])

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        records = self.env["calendar.event"].search([])
        new_records = records - existing_records
        self.assertEqual(len(new_records), 1)
        self.assert_odoo_event(new_records, self.expected_odoo_event_from_outlook)
        self.assertEqual(new_records.user_id, self.organizer_user)

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_create_simple_event_from_outlook_attendee_calendar_and_organizer_does_not_exist_in_odoo(
        self, mock_get_events
    ):

        outlook_event = self.simple_event_from_outlook_attendee
        outlook_event = dict(
            self.simple_event_from_outlook_attendee,
            organizer={
                "emailAddress": {"address": "john.doe@odoo.com", "name": "John Doe"},
            },
        )
        expected_event = dict(self.expected_odoo_event_from_outlook, user_id=False)

        mock_get_events.return_value = (MicrosoftEvent([outlook_event]), None)
        existing_records = self.env["calendar.event"].search([])

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        records = self.env["calendar.event"].search([])
        new_records = records - existing_records
        self.assertEqual(len(new_records), 1)
        self.assert_odoo_event(new_records, expected_event)

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_create_simple_event_from_outlook_attendee_calendar_where_email_addresses_are_capitalized(
        self, mock_get_events
    ):

        outlook_event = dict(
            self.simple_event_from_outlook_attendee,
            organizer={
                "emailAddress": {
                    "address": "Mike@organizer.com",
                    "name": "Mike Organizer",
                },
            },
            attendees=[
                {
                    "type": "required",
                    "status": {"response": "none", "time": "0001-01-01T00:00:00Z"},
                    "emailAddress": {
                        "name": "John Attendee",
                        "address": "John@attendee.com",
                    },
                }
            ],
        )

        mock_get_events.return_value = (MicrosoftEvent([outlook_event]), None)
        existing_records = self.env["calendar.event"].search([])

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        records = self.env["calendar.event"].search([])
        new_records = records - existing_records
        self.assertEqual(len(new_records), 1)
        self.assert_odoo_event(new_records, self.expected_odoo_event_from_outlook)
        self.assertEqual(new_records.user_id, self.organizer_user)

    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_recurrent_event_without_sync(self, mock_insert):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return

        self.organizer_user._calendar_sync_account("microsoft").stopped = True

        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.recurrent_event_values)
        )
        self.call_post_commit_hooks()
        record.invalidate_recordset()

        mock_insert.assert_not_called()
        self.assertFalse(self.microsoft_link(record, self.organizer_user))

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_recurrent_event_with_sync(self, mock_insert, mock_get_events):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return

        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.recurrent_event_values)
        )

        recurrence = self.env["calendar.recurrence"].search(
            [("base_event_id", "=", record.id)]
        )

        mock_insert.assert_not_called()
        self.assertEqual(record.name, "recurring_event")
        self.assertEqual(recurrence.name, "Every 2 Days for 7 events")
        self.assertEqual(len(recurrence.calendar_event_ids), 7)

        event_id = "123"
        event_iCalUId = "456"
        mock_insert.return_value = {"id": event_id, "iCalUId": event_iCalUId}
        mock_get_events.return_value = ([], None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )
        self.call_post_commit_hooks()
        recurrence.invalidate_recordset()

        self.assertEqual(self.held_id(recurrence), event_id)
        self.assertEqual(self.held_id(recurrence, "universal_id"), event_iCalUId)
        self.assertFalse(self.awaits_push(recurrence))

        mock_insert.assert_called_once()
        self.assert_dict_equal(
            mock_insert.call_args[0][0], self.recurrent_event_ms_values
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_recurrent_event_with_sync_by_another_user(
        self, mock_insert, mock_get_events
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return

        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.recurrent_event_values)
        )

        recurrence = self.env["calendar.recurrence"].search(
            [("base_event_id", "=", record.id)]
        )

        mock_insert.assert_not_called()
        self.assertEqual(record.name, "recurring_event")
        self.assertEqual(
            recurrence.name, f"Every 2 Days for {self.recurrent_events_count} events"
        )
        self.assertEqual(
            len(recurrence.calendar_event_ids), self.recurrent_events_count
        )

        event_id = "123"
        event_iCalUId = "456"
        mock_insert.return_value = {"id": event_id, "iCalUId": event_iCalUId}
        mock_get_events.return_value = ([], None)

        self.attendee_user.with_user(self.attendee_user).sudo()._calendar_sync_run(
            "microsoft"
        )
        self.call_post_commit_hooks()
        recurrence.invalidate_recordset()

        mock_insert.assert_not_called()

        self.assertEqual(self.held_id(recurrence), False)
        self.assertEqual(self.held_id(recurrence, "universal_id"), False)
        self.assertFalse(self.awaits_push(recurrence))

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_create_recurrent_event_from_outlook_organizer_calendar(
        self, mock_get_events
    ):

        mock_get_events.return_value = (
            MicrosoftEvent(self.recurrent_event_from_outlook_organizer),
            None,
        )
        existing_events = self.env["calendar.event"].search([])
        existing_recurrences = self.env["calendar.recurrence"].search([])

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        new_events = self.env["calendar.event"].search([]) - existing_events
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )
        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(len(new_events), self.recurrent_events_count)
        self.assert_odoo_recurrence(
            new_recurrences, self.expected_odoo_recurrency_from_outlook
        )
        for i, e in enumerate(sorted(new_events, key=lambda e: e.id)):
            self.assert_odoo_event(
                e, self.expected_odoo_recurrency_events_from_outlook[i]
            )

    def _sync_outlook_series(self, mock_get_events, pattern, starts):
        def timed(item, start):
            item["start"]["dateTime"] = start.strftime("%Y-%m-%dT%H:%M:%S.0000000")
            item["end"]["dateTime"] = (start + timedelta(hours=1)).strftime(
                "%Y-%m-%dT%H:%M:%S.0000000"
            )
            return item

        master, occurrence = self.recurrent_event_from_outlook_organizer[:2]
        master = timed(deepcopy(master), starts[0])
        master["recurrence"] = {
            "pattern": {
                "month": 0,
                "dayOfMonth": 0,
                "daysOfWeek": [],
                "firstDayOfWeek": "sunday",
                "index": "first",
                **pattern,
            },
            "range": {
                "type": "numbered",
                "startDate": starts[0].strftime("%Y-%m-%d"),
                "endDate": "0001-01-01",
                "recurrenceTimeZone": "UTC",
                "numberOfOccurrences": len(starts),
            },
        }
        occurrences = [
            dict(
                timed(deepcopy(occurrence), start),
                id=f"REC123_EVENT_{index}",
                iCalUId=f"REC456_EVENT_{index}",
            )
            for index, start in enumerate(starts)
        ]
        mock_get_events.return_value = (MicrosoftEvent([master, *occurrences]), None)
        existing_recurrences = self.env["calendar.recurrence"].search([])
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )
        recurrence = self.env["calendar.recurrence"].search([]) - existing_recurrences
        self.assertEqual(
            recurrence.calendar_event_ids.sorted("start").mapped("start"), starts
        )
        return recurrence

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_outlook_last_day_of_the_month_round_trips(self, mock_get_events):
        pattern = {
            "type": "relativeMonthly",
            "interval": 1,
            "daysOfWeek": [
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            ],
            "index": "last",
        }
        recurrence = self._sync_outlook_series(
            mock_get_events,
            pattern,
            [
                datetime(2024, 1, 31, 10, 0),
                datetime(2024, 2, 29, 10, 0),
                datetime(2024, 3, 31, 10, 0),
            ],
        )
        self.assertEqual((recurrence.month_by, recurrence.day), ("date", -1))
        self.assertEqual(recurrence.rrule, "FREQ=MONTHLY;COUNT=3;BYMONTHDAY=-1")
        self.assertEqual(recurrence._get_microsoft_pattern(), pattern)

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_outlook_yearly_nth_weekday_round_trips(self, mock_get_events):
        pattern = {
            "type": "relativeYearly",
            "interval": 1,
            "daysOfWeek": ["sunday"],
            "index": "second",
            "month": 3,
        }
        recurrence = self._sync_outlook_series(
            mock_get_events,
            pattern,
            [
                datetime(2024, 3, 10, 10, 0),
                datetime(2025, 3, 9, 10, 0),
                datetime(2026, 3, 8, 10, 0),
            ],
        )
        self.assertEqual(
            (
                recurrence.repeat_unit,
                recurrence.month_by,
                recurrence.weekday,
                recurrence.byday,
            ),
            ("year", "day", "SUN", "2"),
        )
        self.assertEqual(recurrence.rrule, "FREQ=YEARLY;COUNT=3;BYMONTH=3;BYDAY=+2SU")
        self.assertEqual(
            recurrence.name, "Every 1 Years on the Second Sunday of March for 3 events"
        )
        self.assertEqual(recurrence._get_microsoft_pattern(), pattern)

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_outlook_yearly_on_its_start_date_round_trips(self, mock_get_events):
        pattern = {
            "type": "absoluteYearly",
            "interval": 1,
            "month": 3,
            "dayOfMonth": 10,
        }
        recurrence = self._sync_outlook_series(
            mock_get_events,
            pattern,
            [datetime(2024, 3, 10, 10, 0), datetime(2025, 3, 10, 10, 0)],
        )
        self.assertEqual(
            (recurrence.repeat_unit, recurrence.month_by), ("year", "date")
        )
        self.assertEqual(recurrence._get_microsoft_pattern(), pattern)

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_outlook_last_weekday_of_the_month_round_trips(self, mock_get_events):
        pattern = {
            "type": "relativeMonthly",
            "interval": 1,
            "daysOfWeek": ["monday", "tuesday", "wednesday", "thursday", "friday"],
            "index": "last",
        }
        recurrence = self._sync_outlook_series(
            mock_get_events,
            pattern,
            [
                datetime(2024, 1, 31, 10, 0),
                datetime(2024, 2, 29, 10, 0),
                datetime(2024, 3, 29, 10, 0),
            ],
        )
        self.assertEqual(
            recurrence.custom_rrule, "FREQ=MONTHLY;BYSETPOS=-1;BYDAY=MO,TU,WE,TH,FR"
        )
        self.assertEqual(
            recurrence.rrule, "FREQ=MONTHLY;COUNT=3;BYSETPOS=-1;BYDAY=MO,TU,WE,TH,FR"
        )
        self.assertEqual(recurrence._get_microsoft_pattern(), pattern)
        self.assertIsNone(recurrence._microsoft_refusal())

    def _sync_outlook_biweekly_sunday_and_monday(
        self, mock_get_events, first_day, starts
    ):
        pattern = {
            "type": "weekly",
            "interval": 2,
            "daysOfWeek": ["monday", "sunday"],
            "firstDayOfWeek": first_day,
        }
        recurrence = self._sync_outlook_series(mock_get_events, pattern, starts)
        self.assertEqual(recurrence._get_microsoft_pattern(), pattern)
        return recurrence

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_outlook_weeks_starting_on_sunday_round_trip(self, mock_get_events):
        recurrence = self._sync_outlook_biweekly_sunday_and_monday(
            mock_get_events,
            "sunday",
            [
                datetime(2024, 1, 7, 10, 0),
                datetime(2024, 1, 8, 10, 0),
                datetime(2024, 1, 21, 10, 0),
                datetime(2024, 1, 22, 10, 0),
            ],
        )
        self.assertEqual(recurrence.week_start, "SUN")

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_outlook_weeks_starting_on_monday_round_trip(self, mock_get_events):
        recurrence = self._sync_outlook_biweekly_sunday_and_monday(
            mock_get_events,
            "monday",
            [
                datetime(2024, 1, 7, 10, 0),
                datetime(2024, 1, 15, 10, 0),
                datetime(2024, 1, 21, 10, 0),
                datetime(2024, 1, 29, 10, 0),
            ],
        )
        self.assertEqual(recurrence.week_start, "MON")

    def test_a_rule_outlook_cannot_hold_is_refused(self):
        self.organizer_user._calendar_sync_account("microsoft").stopped = True
        event = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(
                {
                    "name": "First and third Monday",
                    "start": datetime(2024, 1, 1, 10, 0),
                    "stop": datetime(2024, 1, 1, 11, 0),
                    "recurrency": True,
                    "rrule": "FREQ=MONTHLY;BYDAY=1MO,3MO;COUNT=4",
                    "event_tz": "UTC",
                }
            )
        )
        self.assertEqual(
            event.recurrence_id.custom_rrule, "FREQ=MONTHLY;BYDAY=+1MO,+3MO"
        )
        self.assertIn(
            "FREQ=MONTHLY;BYDAY=+1MO,+3MO", event.recurrence_id._microsoft_refusal()
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_create_recurrent_event_from_outlook_attendee_calendar(
        self, mock_get_events
    ):

        mock_get_events.return_value = (
            MicrosoftEvent(self.recurrent_event_from_outlook_attendee),
            None,
        )
        existing_events = self.env["calendar.event"].search([])
        existing_recurrences = self.env["calendar.recurrence"].search([])

        self.attendee_user.with_user(self.attendee_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        new_events = self.env["calendar.event"].search([]) - existing_events
        new_recurrences = (
            self.env["calendar.recurrence"].search([]) - existing_recurrences
        )
        self.assertEqual(len(new_recurrences), 1)
        self.assertEqual(len(new_events), self.recurrent_events_count)
        self.assert_odoo_recurrence(
            new_recurrences, self.expected_odoo_recurrency_from_outlook
        )
        for i, e in enumerate(sorted(new_events, key=lambda e: e.id)):
            self.assert_odoo_event(
                e, self.expected_odoo_recurrency_events_from_outlook[i]
            )

    @patch.object(MicrosoftCalendarService, "insert")
    def test_forbid_recurrences_creation_synced_outlook_calendar(self, mock_insert):

        self.assertFalse(self.env.user._calendar_sync_account("microsoft").stopped)

        with self.assertRaises(UserError):
            self.env["calendar.event"].create(self.recurrent_event_values)
        mock_insert.assert_not_called()

    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_event_with_sync_config_paused(self, mock_insert):
        self.organizer_user._calendar_sync_account("microsoft").stopped = False
        self.env["calendar.sync.account"]._set_paused("microsoft", True)

        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        self.call_post_commit_hooks()
        record.invalidate_recordset()

        self.assertFalse(
            self.organizer_user._calendar_sync_account("microsoft").stopped
        )
        self.assertEqual(
            self.organizer_user._calendar_sync_status("microsoft"), "sync_paused"
        )
        self.assertTrue(
            self.awaits_push(record),
            "The event waits for the synchronization to resume",
        )
        mock_insert.assert_not_called()

    @patch.object(MicrosoftCalendarService, "patch")
    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_sync_create_update_single_event(
        self, mock_insert, mock_get_events, mock_patch
    ):
        self.organizer_user.with_user(self.organizer_user).sudo().calendar_sync_stop(
            "microsoft"
        )
        event = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(
                dict(
                    self.simple_event_values,
                    start=datetime.now() + timedelta(days=1),
                    stop=datetime.now() + timedelta(days=1, hours=1),
                )
            )
        )
        self.call_post_commit_hooks()
        mock_insert.assert_not_called()

        mock_get_events.return_value = (MicrosoftEvent(), None)
        mock_insert.return_value = {"id": "123_restarted", "iCalUId": "456_restarted"}
        self.organizer_user.with_user(self.organizer_user).sudo().calendar_sync_restart(
            "microsoft"
        )
        self.sync_microsoft(self.organizer_user)
        mock_insert.assert_called_once()
        self.assertEqual(self.microsoft_id(event, self.organizer_user), "123_restarted")

        event.with_user(self.organizer_user).write({"name": "New event name"})
        self.call_post_commit_hooks()
        mock_insert.assert_called_once()
        mock_patch.assert_called_once()
        self.assertEqual(mock_patch.call_args[0][0], "123_restarted")

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_event_for_another_user(self, mock_insert, mock_get_events):
        self.assertTrue(
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            ._check_microsoft_sync_status()
        )
        self.attendee_user._calendar_sync_account("microsoft").stopped = True

        self.simple_event_values["user_id"] = self.attendee_user.id
        self.simple_event_values["partner_ids"] = [
            Command.set([self.organizer_user.partner_id.id])
        ]
        with self.assertRaises(ValidationError):
            self.env["calendar.event"].with_user(self.organizer_user).create(
                self.simple_event_values
            )

        self.attendee_user._calendar_sync_account("microsoft").stopped = False
        self.assertTrue(
            self.env["calendar.event"]
            .with_user(self.attendee_user)
            ._check_microsoft_sync_status()
        )

        with self.assertRaises(ValidationError):
            self.env["calendar.event"].with_user(self.organizer_user).create(
                self.simple_event_values
            )

        event_id = "123"
        event_iCalUId = "456"
        mock_insert.return_value = {"id": event_id, "iCalUId": event_iCalUId}
        mock_get_events.return_value = ([], None)

        self.simple_event_values["partner_ids"] = [
            Command.set(
                [self.organizer_user.partner_id.id, self.attendee_user.partner_id.id]
            )
        ]
        event = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        self.call_post_commit_hooks()
        event.invalidate_recordset()

        mock_insert.assert_called_once()
        self.assertEqual(
            event.user_id,
            self.attendee_user,
            "Event organizer must be user B (self.attendee_user) after event creation by user A (self.organizer_user).",
        )
        self.assertTrue(
            self.attendee_user.partner_id.id in event.partner_ids.ids,
            "User B (self.attendee_user) should be listed as attendee after event creation.",
        )

        portal_group = self.env.ref("base.group_portal")
        portal_user = self.env["res.users"].create(
            {
                "login": "portal@user",
                "email": "portal@user",
                "name": "PortalUser",
                "group_ids": [Command.set([portal_group.id])],
            }
        )

        self.simple_event_from_outlook_organizer.update(
            {
                "id": "portalUserEventID",
                "iCalUId": "portalUserEventICalUId",
                "isOrganizer": False,
                "organizer": {
                    "emailAddress": {
                        "address": portal_user.login,
                        "name": portal_user.name,
                    }
                },
            }
        )
        mock_get_events.return_value = (
            MicrosoftEvent([self.simple_event_from_outlook_organizer]),
            None,
        )
        self.assertTrue(
            self.env["calendar.event"]
            .with_user(self.attendee_user)
            ._check_microsoft_sync_status()
        )
        self.attendee_user.with_user(self.attendee_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        portal_user_events = self.env["calendar.event"].search(
            [("user_id", "=", portal_user.id)]
        )
        self.assertEqual(len(portal_user_events), 1)

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_create_simple_event_from_outlook_without_organizer(self, mock_get_events):

        outlook_event = self.simple_event_from_outlook_attendee
        outlook_event = dict(self.simple_event_from_outlook_attendee, organizer=None)
        expected_event = dict(self.expected_odoo_event_from_outlook, user_id=False)

        mock_get_events.return_value = (MicrosoftEvent([outlook_event]), None)
        existing_records = self.env["calendar.event"].search([])

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        records = self.env["calendar.event"].search([])
        new_records = records - existing_records
        self.assertEqual(len(new_records), 1)
        self.assert_odoo_event(new_records, expected_event)

    def test_create_event_with_default_and_undefined_sensitivity(self):
        self.simple_event_from_outlook_organizer.pop("sensitivity")
        undefined_privacy_event = {
            **self.simple_event_from_outlook_organizer,
            "id": "100",
            "iCalUId": "2",
        }
        default_privacy_event = {
            **self.simple_event_from_outlook_organizer,
            "id": "200",
            "iCalUId": "4",
            "sensitivity": None,
        }
        self.apply_microsoft(
            [undefined_privacy_event, default_privacy_event], self.organizer_user
        )

        undefined_privacy_odoo_event = self.find_microsoft("calendar.event", "=", "100")
        default_privacy_odoo_event = self.find_microsoft("calendar.event", "=", "200")
        self.assertFalse(
            undefined_privacy_odoo_event.privacy,
            "Event with undefined privacy must have False value in privacy field.",
        )
        self.assertFalse(
            default_privacy_odoo_event.privacy,
            "Event with custom privacy must have False value in privacy field.",
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_videocall_sync_microsoft_calendar(
        self, mock_insert, mock_get_events
    ):
        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        self.assertEqual(
            record.name, "simple_event", "Event name should be same as simple_event"
        )

        event_id = "123"
        event_iCalUId = "456"
        mock_insert.return_value = {"id": event_id, "iCalUId": event_iCalUId}
        self.call_post_commit_hooks()

        self.response_from_outlook_organizer = {
            **self.simple_event_from_outlook_organizer,
            "onlineMeeting": {
                "joinUrl": "https://teams.microsoft.com/l/meetup-join/test",
                "conferenceId": "275984951",
                "tollNumber": "+1 323-555-0166",
            },
            "lastModifiedDateTime": _modified_date_in_the_future(record),
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness",
        }
        mock_get_events.return_value = (
            MicrosoftEvent([self.response_from_outlook_organizer]),
            None,
        )
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )
        self.call_post_commit_hooks()
        record.invalidate_recordset()

        mock_insert.assert_called_once()
        self.assertEqual(
            self.held_id(record),
            event_id,
            "The Microsoft ID should be assigned to the event.",
        )
        self.assertEqual(self.held_id(record, "universal_id"), event_iCalUId)
        self.assertEqual(
            mock_insert.call_args[0][0].get("isOnlineMeeting"),
            True,
            "The event should be marked as an online meeting.",
        )
        self.assertEqual(
            mock_insert.call_args[0][0].get("onlineMeetingProvider"),
            "teamsForBusiness",
            "The event's online meeting provider should be set to Microsoft Teams.",
        )
        self.assertFalse(self.awaits_push(record))

        event = self.env["calendar.event"].search(
            [("name", "=", self.response_from_outlook_organizer.get("subject"))]
        )
        self.assertTrue(event, "The event should exist in the calendar after sync.")
        self.assertEqual(
            event.videocall_location,
            "https://teams.microsoft.com/l/meetup-join/test",
            "The meeting URL should match.",
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_no_videocall_hr_holidays(self, mock_insert, mock_get_events):
        if self.env["ir.module.module"]._get("hr_holidays").state not in [
            "installed",
            "to upgrade",
        ]:
            self.skipTest(
                "The 'hr_holidays' module must be installed to run this test."
            )

        self.user_hrmanager = mail_new_test_user(
            self.env,
            login="bastien",
            groups="base.group_user,hr_holidays.group_hr_holidays_manager",
        )
        self.user_employee = mail_new_test_user(
            self.env, login="enguerran", password="enguerran", groups="base.group_user"
        )
        self.rd_dept = (
            self.env["hr.department"]
            .with_context(tracking_disable=True)
            .create(
                {
                    "name": "Research and Development",
                }
            )
        )
        self.employee_emp = self.env["hr.employee"].create(
            {
                "name": "Marc Demo",
                "user_id": self.user_employee.id,
                "department_id": self.rd_dept.id,
            }
        )
        self.hr_leave_type = (
            self.env["hr.leave.type"]
            .with_user(self.user_hrmanager)
            .create(
                {
                    "name": "Time Off Type",
                    "requires_allocation": False,
                }
            )
        )
        today = datetime.now()
        day = today.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
            days=7 + (2 - today.weekday()) % 7
        )
        self.holiday = (
            self.env["hr.leave"]
            .with_context(mail_create_nolog=True, mail_notrack=True)
            .with_user(self.user_employee)
            .create(
                {
                    "name": "Time Off Employee",
                    "employee_id": self.employee_emp.id,
                    "holiday_status_id": self.hr_leave_type.id,
                    "request_date_from": day,
                    "request_date_to": day,
                }
            )
        )
        self.holiday.with_user(self.user_hrmanager).action_approve()

        search_domain = [
            ("name", "like", self.holiday.employee_id.name),
            ("start_date", ">=", self.holiday.request_date_from),
            ("stop_date", "<=", self.holiday.request_date_to),
        ]
        record = self.env["calendar.event"].search(search_domain)
        self.assertTrue(record, "The time off event should exist.")
        self.assertEqual(
            record.name,
            "Marc Demo on Time Off : 1 days",
            "The event name should match the employee's time off description.",
        )
        self.assertEqual(
            record.start_date,
            day.date(),
            "The start date should match the time off request.",
        )
        self.assertEqual(
            record.stop_date,
            day.date(),
            "The end date should match the time off request.",
        )

        event_id = "123"
        event_iCalUId = "456"
        mock_insert.return_value = {"id": event_id, "iCalUId": event_iCalUId}
        mock_get_events.return_value = ([], None)

        self.user_employee.with_user(self.user_employee).sudo()._calendar_sync_run(
            "microsoft"
        )
        self.call_post_commit_hooks()
        record.invalidate_recordset()
        mock_insert.assert_called_once()

        self.assertEqual(
            self.held_id(record),
            event_id,
            "The Microsoft ID should be assigned correctly.",
        )
        self.assertEqual(
            self.held_id(record, "universal_id"),
            event_iCalUId,
            "The iCalUID should be assigned correctly.",
        )
        self.assertFalse(
            self.awaits_push(record),
            "The event should no longer need synchronization.",
        )
        self.assertEqual(
            mock_insert.call_args[0][0].get("isOnlineMeeting"),
            False,
            "Time off events should not be marked as an online meeting.",
        )
        self.assertFalse(
            mock_insert.call_args[0][0].get("onlineMeetingProvider", False)
        )

    @patch.object(
        MicrosoftCalendarService, "get_events", return_value=(MicrosoftEvent(), None)
    )
    @patch.object(MicrosoftCalendarService, "insert")
    def test_skip_sync_for_non_synchronized_users_new_events(
        self, mock_insert, mock_get_events
    ):
        with self.mock_datetime_and_now("2021-09-20 10:00:00"):
            self.assertTrue(
                self.env["calendar.event"]
                .with_user(self.attendee_user)
                ._check_microsoft_sync_status()
            )
            self.organizer_user._calendar_sync_account("microsoft").stopped = True

            self.simple_event_values["user_id"] = self.organizer_user.id
            self.simple_event_values["partner_ids"] = [
                Command.set(
                    [
                        self.organizer_user.partner_id.id,
                        self.attendee_user.partner_id.id,
                    ]
                )
            ]
            event = (
                self.env["calendar.event"]
                .with_user(self.organizer_user)
                .create(self.simple_event_values)
            )
            self.assertTrue(
                event,
                "The event for the not synchronized owner must be created in Odoo.",
            )

            self.sync_microsoft(self.attendee_user)
            mock_insert.assert_not_called()

            event_id = "123"
            event_iCalUId = "456"
            mock_insert.return_value = {"id": event_id, "iCalUId": event_iCalUId}

            self.organizer_user._calendar_sync_account("microsoft").stopped = False
            self.organizer_user.with_user(self.organizer_user).calendar_sync_restart(
                "microsoft"
            )
            self.sync_microsoft(self.organizer_user)
            mock_insert.assert_called()

    @patch.object(MicrosoftCalendarService, "insert")
    def test_an_insert_carries_the_transaction_id_its_retry_repeats(self, mock_insert):
        mock_insert.side_effect = [
            requests.Timeout(),
            {"id": "123_once", "iCalUId": "456_once"},
        ]
        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        self.call_post_commit_hooks()
        link = self.microsoft_link(record, self.organizer_user)
        self.assertFalse(link.remote_id)
        self.assertEqual(mock_insert.call_args[0][0]["transactionId"], link.insert_id)

        record._calendar_sync_queue(["microsoft"])
        self.call_post_commit_hooks()
        self.assertEqual(mock_insert.call_count, 2)
        first, second = (
            call[0][0]["transactionId"] for call in mock_insert.call_args_list
        )
        self.assertEqual(first, second)
        self.assertEqual(self.microsoft_id(record, self.organizer_user), "123_once")

    @patch.object(MicrosoftCalendarService, "insert")
    def test_create_duplicate_event_microsoft_calendar(self, mock_insert):
        record = (
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            .create(self.simple_event_values)
        )
        mock_insert.side_effect = distinct_inserts("duplicate")
        record2 = record.copy()
        self.call_post_commit_hooks()

        self.assertEqual(mock_insert.call_count, 2)
        self.assertNotEqual(
            self.microsoft_id(record, self.organizer_user),
            self.microsoft_id(record2, self.organizer_user),
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_new_db_skip_odoo2microsoft_sync_previously_created_events(
        self, mock_insert, mock_get_events
    ):
        with (
            patch.object(
                CalendarSyncUsers,
                "_calendar_sync_connection",
                lambda user, code: self.env["integration.connection"],
            ),
            self.mock_datetime_and_now("2024-01-01 10:00:00"),
        ):
            event = (
                self.env["calendar.event"]
                .with_user(self.organizer_user)
                .create(
                    {
                        "name": "Odoo Local Event",
                        "start": datetime(2024, 1, 1, 11, 0),
                        "stop": datetime(2024, 1, 1, 13, 0),
                        "user_id": self.organizer_user.id,
                        "partner_ids": [(4, self.organizer_user.partner_id.id)],
                    }
                )
            )
            self.call_post_commit_hooks()

        with self.mock_datetime_and_now("2024-01-02 10:00:10"):
            mock_get_events.return_value = (MicrosoftEvent(), None)
            self.sync_microsoft(self.organizer_user)
        self.assertTrue(event.exists())
        mock_insert.assert_not_called()

    @patch.object(MicrosoftCalendarService, "get_events")
    @patch.object(MicrosoftCalendarService, "insert")
    def test_old_db_odoo2microsoft_sync_previously_created_events(
        self, mock_insert, mock_get_events
    ):
        with self.mock_datetime_and_now("2024-01-01 10:00:00"):
            self.organizer_user._calendar_sync_account("microsoft").stopped = True
            event = (
                self.env["calendar.event"]
                .with_user(self.organizer_user)
                .create(
                    {
                        "name": "Odoo Local Event",
                        "start": datetime(2024, 1, 1, 11, 0),
                        "stop": datetime(2024, 1, 1, 13, 0),
                        "user_id": self.organizer_user.id,
                        "partner_ids": [(4, self.organizer_user.partner_id.id)],
                    }
                )
            )

            self.attendee_user._calendar_sync_account(
                "microsoft"
            ).sync_token = "OngoingToken"

            mock_get_events.return_value = ([], None)
            mock_insert.return_value = {
                "id": "LocalEventSyncID",
                "iCalUId": "event_iCalUId",
            }
            self.organizer_user._calendar_sync_account("microsoft").stopped = False
            self.assertTrue(
                self.env["calendar.event"]
                .with_user(self.organizer_user)
                ._check_microsoft_sync_status()
            )

            self.organizer_user.with_user(
                self.organizer_user
            ).sudo()._calendar_sync_run("microsoft")
            self.call_post_commit_hooks()
            event.invalidate_recordset()
            mock_insert.assert_called_once()
            self.assertEqual(mock_insert.call_args[0][0]["subject"], event.name)
