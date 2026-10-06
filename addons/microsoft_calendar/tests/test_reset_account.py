from unittest.mock import ANY, patch

from odoo.addons.base.models.ir_cron import IrCron
from odoo.addons.microsoft_calendar.models.res_users import ResUsers
from odoo.addons.microsoft_calendar.tests.common import (
    TestCommon,
    mock_get_token,
    patch_api,
)
from odoo.addons.microsoft_calendar.utils.microsoft_calendar import (
    MicrosoftCalendarService,
)


@patch.object(IrCron, "_commit_progress", lambda self, *a, **kw: None)
@patch.object(ResUsers, "_get_microsoft_calendar_token", mock_get_token)
class TestResetAccount(TestCommon):
    """The wizard cleared `microsoft_id` but kept `ms_universal_event_id`, the
    id `_filtered_synced` reads, so a reset event still counted as synced and
    was patched or deleted at `/events/False`."""

    @patch_api
    def setUp(self):
        super().setUp()
        self.create_events_for_tests()

    def _reset(self, delete_policy, sync_policy):
        self.env["wizard.res.users.reset.microsoft.calendar"].create(
            {
                "user_id": self.organizer_user.id,
                "delete_policy": delete_policy,
                "sync_policy": sync_policy,
            }
        ).reset_account()

    def test_synchronizing_all_again_inserts_instead_of_patching(self):
        self._reset("dont_delete", "all")

        self.assertFalse(self.simple_event.microsoft_id)
        self.assertFalse(self.simple_event.ms_universal_event_id)
        self.assertTrue(self.simple_event.need_sync_m)
        self.assertFalse(self.simple_event._filtered_synced())

    def test_synchronizing_only_new_events_leaves_existing_ones(self):
        self.simple_event.need_sync_m = True

        self._reset("dont_delete", "new")

        self.assertFalse(self.simple_event.need_sync_m)

    @patch.object(MicrosoftCalendarService, "delete")
    def test_deleting_from_odoo_only_calls_nothing_in_outlook(self, mock_delete):
        self._reset("delete_odoo", "new")
        self.call_post_commit_hooks()

        self.assertFalse(self.simple_event.exists())
        mock_delete.assert_not_called()

    @patch.object(MicrosoftCalendarService, "delete")
    def test_deleting_from_outlook_only_unlinks_the_kept_event(self, mock_delete):
        self._reset("delete_microsoft", "new")
        self.call_post_commit_hooks()

        mock_delete.assert_any_call("123", token=ANY, timeout=ANY)
        self.assertTrue(self.simple_event.exists())
        self.assertFalse(self.simple_event.microsoft_id)
        self.assertFalse(self.simple_event.ms_universal_event_id)
