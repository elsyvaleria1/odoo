from unittest.mock import ANY, call, patch

from odoo.exceptions import UserError
from odoo.tools.authority_keys import is_authority_key

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


@patch.object(CalendarSyncUsers, "_calendar_sync_connection", mock_get_connection)
class TestDeleteEvents(TestCommon):
    def setUp(self):
        super().setUp()
        self.create_events_for_tests()

    @patch.object(MicrosoftCalendarService, "delete")
    def test_delete_simple_event_from_odoo_organizer_calendar(self, mock_delete):
        event_id = self.held_id(self.simple_event)

        self.simple_event.with_user(self.organizer_user).unlink()
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertFalse(self.simple_event.exists())
        mock_delete.assert_called_once_with(
            event_id, connection=mock_get_connection(self.organizer_user), timeout=ANY
        )

    @patch.object(MicrosoftCalendarService, "delete")
    def test_delete_simple_event_from_odoo_attendee_calendar(self, mock_delete):
        event_id = self.held_id(self.simple_event)

        self.simple_event.with_user(self.attendee_user).unlink()
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertFalse(self.simple_event.exists())
        mock_delete.assert_called_once_with(
            event_id, connection=mock_get_connection(self.organizer_user), timeout=ANY
        )

    def test_an_attendee_removing_the_event_in_outlook_declines_it(self):
        self.link_microsoft(
            self.simple_event, self.attendee_user, "attendee_123", "456"
        )
        self.apply_microsoft(
            [{"id": "attendee_123", "@removed": {"reason": "deleted"}}],
            self.attendee_user,
        )

        self.assertTrue(self.simple_event.exists())
        attendee = self.simple_event.attendee_ids.filtered(
            lambda a: a.partner_id == self.attendee_user.partner_id
        )
        self.assertEqual(attendee.state, "declined")

    @patch.object(MicrosoftCalendarService, "delete")
    def test_archive_simple_event_from_odoo_organizer_calendar(self, mock_delete):
        event_id = self.held_id(self.simple_event)

        self.simple_event.with_user(self.organizer_user).write({"active": False})
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertTrue(self.simple_event.exists())
        self.assertFalse(self.simple_event.active)
        mock_delete.assert_called_once_with(
            event_id, connection=mock_get_connection(self.organizer_user), timeout=ANY
        )

    @patch.object(MicrosoftCalendarService, "delete")
    def test_archive_simple_event_from_odoo_attendee_calendar(self, mock_delete):
        event_id = self.held_id(self.simple_event)

        self.simple_event.with_user(self.attendee_user).write({"active": False})
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertTrue(self.simple_event.exists())
        self.assertFalse(self.simple_event.active)
        mock_delete.assert_called_once_with(
            event_id, connection=mock_get_connection(self.organizer_user), timeout=ANY
        )

    @patch.object(MicrosoftCalendarService, "delete")
    def test_archive_several_events_at_once(self, mock_delete):
        several_simple_events = self.several_events.filtered(
            lambda ev: not ev.recurrency and self.held_id(ev)
        )
        remote_ids = [self.held_id(event) for event in several_simple_events]
        several_simple_events.action_archive()
        self.call_post_commit_hooks()
        several_simple_events.invalidate_recordset()

        self.assertFalse(all(e.active for e in several_simple_events))

        mock_delete.assert_has_calls(
            [call(remote_id, connection=ANY, timeout=ANY) for remote_id in remote_ids]
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_cancel_simple_event_from_outlook_organizer_calendar(self, mock_get_events):
        event_id = self.held_id(self.simple_event)
        mock_get_events.return_value = (
            MicrosoftEvent([{"id": event_id, "@removed": {"reason": "deleted"}}]),
            None,
        )
        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )
        self.assertFalse(self.simple_event.exists())

    def test_delete_simple_event_from_outlook_attendee_calendar(self):
        pass

    @patch.object(MicrosoftCalendarService, "delete")
    def test_delete_one_event_from_recurrence_from_odoo_calendar(self, mock_delete):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        idx = 2
        event_id = self.held_id(self.recurrent_events[idx])

        self.recurrent_events[idx].with_user(self.organizer_user).unlink()
        self.call_post_commit_hooks()

        self.assertFalse(self.recurrent_events[idx].exists())
        self.assertEqual(
            len(self.recurrence.calendar_event_ids), self.recurrent_events_count - 1
        )
        mock_delete.assert_called_once_with(
            event_id, connection=mock_get_connection(self.organizer_user), timeout=ANY
        )

    @patch.object(MicrosoftCalendarService, "delete")
    def test_delete_first_event_from_recurrence_from_odoo_calendar(self, mock_delete):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        idx = 0
        event_id = self.held_id(self.recurrent_events[idx])

        self.recurrent_events[idx].with_user(self.organizer_user).unlink()
        self.call_post_commit_hooks()

        self.assertFalse(self.recurrent_events[idx].exists())
        self.assertEqual(
            len(self.recurrence.calendar_event_ids), self.recurrent_events_count - 1
        )
        self.assertEqual(self.recurrence.base_event_id, self.recurrent_events[1])
        mock_delete.assert_called_once_with(
            event_id, connection=mock_get_connection(self.organizer_user), timeout=ANY
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_delete_one_event_from_recurrence_from_outlook_calendar(
        self, mock_get_events
    ):
        idx = 3
        rec_values = [
            dict(
                event,
                lastModifiedDateTime=_modified_date_in_the_future(self.recurrence),
            )
            for i, event in enumerate(self.recurrent_event_from_outlook_organizer)
            if i != (idx + 1)
        ]
        event_to_remove = self.recurrent_events[idx]
        mock_get_events.return_value = (MicrosoftEvent(rec_values), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        self.assertFalse(event_to_remove.exists())
        self.assertEqual(
            len(self.recurrence.calendar_event_ids), self.recurrent_events_count - 1
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_delete_first_event_from_recurrence_from_outlook_calendar(
        self, mock_get_events
    ):
        rec_values = [
            dict(
                event,
                lastModifiedDateTime=_modified_date_in_the_future(self.recurrence),
            )
            for i, event in enumerate(self.recurrent_event_from_outlook_organizer)
            if i != 1
        ]
        event_to_remove = self.recurrent_events[0]
        next_base_event = self.recurrent_events[1]
        mock_get_events.return_value = (MicrosoftEvent(rec_values), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        self.assertFalse(event_to_remove.exists())
        self.assertEqual(
            len(self.recurrence.calendar_event_ids), self.recurrent_events_count - 1
        )
        self.assertEqual(self.recurrence.base_event_id, next_base_event)

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_delete_one_event_and_future_from_recurrence_from_outlook_calendar(
        self, mock_get_events
    ):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        idx = range(4, self.recurrent_events_count)
        rec_values = [
            dict(
                event,
                lastModifiedDateTime=_modified_date_in_the_future(self.recurrence),
            )
            for i, event in enumerate(self.recurrent_event_from_outlook_organizer)
            if i not in [x + 1 for x in idx]
        ]
        event_to_remove = [e for i, e in enumerate(self.recurrent_events) if i in idx]
        mock_get_events.return_value = (MicrosoftEvent(rec_values), None)

        self.organizer_user.with_user(self.organizer_user).sudo()._calendar_sync_run(
            "microsoft"
        )

        for e in event_to_remove:
            self.assertFalse(e.exists())
        self.assertEqual(
            len(self.recurrence.calendar_event_ids),
            self.recurrent_events_count - len(idx),
        )

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_delete_first_event_and_future_from_recurrence_from_outlook_calendar(
        self, mock_get_events
    ):
        mock_get_events.return_value = (
            MicrosoftEvent(
                [
                    {
                        "id": self.held_id(self.recurrence),
                        "@removed": {"reason": "deleted"},
                    }
                ]
            ),
            None,
        )

        self.organizer_user.with_context(
            dont_notify=True, microsoft_calendar_syncing=True
        ).with_user(self.organizer_user).sudo()._calendar_sync_run("microsoft")

        self.assertFalse(self.recurrence.exists())
        self.assertFalse(self.recurrence.calendar_event_ids.exists())

    @patch.object(MicrosoftCalendarService, "get_events")
    def test_delete_all_events_from_recurrence_from_outlook_calendar(
        self, mock_get_events
    ):
        pass

    @patch.object(MicrosoftCalendarService, "delete")
    def test_delete_single_event_from_recurrence_from_odoo_calendar(self, mock_delete):
        if not self.sync_odoo_recurrences_with_outlook_feature():
            return
        idx = 0
        event_id = self.held_id(self.recurrent_events[idx])

        self.recurrent_events[idx].with_user(self.organizer_user).action_mass_archive(
            "this"
        )
        self.call_post_commit_hooks()

        self.assertFalse(self.recurrent_events[idx].active)
        self.assertNotEqual(
            self.id, self.recurrent_events[idx].recurrence_id.base_event_id.id
        )
        self.assertTrue(
            self.id
            not in [
                rec.id
                for rec in self.recurrent_events[idx].recurrence_id.calendar_event_ids
            ]
        )
        mock_delete.assert_called_once_with(
            event_id, connection=mock_get_connection(self.organizer_user), timeout=ANY
        )

    @patch.object(MicrosoftCalendarService, "delete")
    def test_delete_synced_event_with_sync_config_paused(self, mock_delete):
        self.organizer_user._calendar_sync_account("microsoft").stopped = False
        self.env["calendar.sync.account"]._set_paused("microsoft", True)

        self.simple_event.with_user(self.organizer_user).unlink()
        self.call_post_commit_hooks()
        self.simple_event.invalidate_recordset()

        self.assertFalse(
            self.organizer_user._calendar_sync_account("microsoft").stopped
        )
        self.assertEqual(
            self.organizer_user._calendar_sync_status("microsoft"), "sync_paused"
        )
        self.assertFalse(
            self.simple_event.exists(),
            "Event must be deleted from Odoo even though sync configuration is off",
        )
        mock_delete.assert_not_called()

    @patch.object(MicrosoftCalendarService, "delete")
    def test_delete_recurrence_previously_synced(self, mock_delete):
        idx = 0

        with self.assertRaises(UserError):
            self.recurrent_events[idx].with_user(
                self.organizer_user
            ).action_mass_archive("all")
            self.call_post_commit_hooks()

        self.assertTrue(
            self.recurrent_events[idx]
            .with_user(self.organizer_user)
            ._check_microsoft_sync_status()
        )
        self.assertTrue(self.recurrent_events[idx].active)
        mock_delete.assert_not_called()

    def test_forbid_recurrence_unlinking_list_view(self):
        self.assertTrue(
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            ._check_microsoft_sync_status()
        )
        with self.assertRaises(UserError):
            self.recurrent_events.unlink()
        with self.assertRaises(UserError):
            self.recurrent_events.with_context(dont_notify=True).unlink()
        self.assertTrue(is_authority_key("microsoft_calendar_syncing"))

        self.recurrent_events[2:].with_context(
            dont_notify=True, microsoft_calendar_syncing=True
        ).unlink()
        self.assertTrue(
            all(not event.exists() for event in self.recurrent_events[2:]),
            "Recurrent event must be deleted after unlink from Microsoft.",
        )

        self.organizer_user._calendar_sync_account("microsoft").stopped = True
        self.assertFalse(
            self.env["calendar.event"]
            .with_user(self.organizer_user)
            ._check_microsoft_sync_status()
        )
        self.recurrent_events[1].with_user(self.organizer_user).unlink()
        self.assertFalse(
            self.recurrent_events[1].exists(),
            "Recurrent event must be deleted after unlink with sync off.",
        )
