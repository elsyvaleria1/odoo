from unittest.mock import ANY, patch

from odoo.addons.base.models.ir_cron import IrCron
from odoo.addons.calendar_microsoft.tests.common import (
    TestCommon,
    mock_get_connection,
)
from odoo.addons.calendar_microsoft.utils.calendar_microsoft import (
    MicrosoftCalendarService,
)
from odoo.addons.calendar_sync.models.res_users import ResUsers as CalendarSyncUsers


@patch.object(IrCron, "_commit_progress", lambda self, *a, **kw: None)
@patch.object(CalendarSyncUsers, "_calendar_sync_connection", mock_get_connection)
class TestResetAccount(TestCommon):

    def setUp(self):
        super().setUp()
        self.create_events_for_tests()

    def _reset(self, delete_policy, sync_policy):
        self.env["wizard.calendar.sync.reset"].create(
            {
                "provider": "microsoft",
                "user_id": self.organizer_user.id,
                "delete_policy": delete_policy,
                "sync_policy": sync_policy,
            }
        ).reset_account()

    def test_synchronizing_all_again_inserts_instead_of_patching(self):
        self._reset("dont_delete", "all")

        self.assertFalse(self.microsoft_link(self.simple_event, self.organizer_user))
        self.assertTrue(self.awaits_push(self.simple_event))
        self.assertFalse(
            self.organizer_user._calendar_sync_account("microsoft").insert_since
        )

    def test_synchronizing_only_new_events_leaves_existing_ones(self):
        self._reset("dont_delete", "new")

        account = self.organizer_user._calendar_sync_account("microsoft")
        self.assertGreaterEqual(account.insert_since, self.simple_event.create_date)
        self.assertFalse(self.microsoft_link(self.simple_event, self.organizer_user))

    @patch.object(MicrosoftCalendarService, "delete")
    def test_deleting_from_odoo_only_calls_nothing_in_outlook(self, mock_delete):
        self._reset("delete_odoo", "new")
        self.call_post_commit_hooks()

        self.assertFalse(self.simple_event.exists())
        mock_delete.assert_not_called()

    @patch.object(MicrosoftCalendarService, "delete")
    def test_deleting_from_outlook_only_unlinks_the_kept_event(self, mock_delete):
        self._reset("delete_remote", "new")
        self.call_post_commit_hooks()

        mock_delete.assert_any_call("123", connection=ANY, timeout=ANY)
        self.assertTrue(self.simple_event.exists())
        self.assertFalse(self.microsoft_link(self.simple_event, self.organizer_user))
