from odoo.exceptions import RedirectWarning, UserError
from odoo.tests import tagged

from odoo.addons.account_online_synchronization.tests.common import (
    AccountOnlineSynchronizationCommon,
)


@tagged("post_install", "-at_install")
class TestOnlineStateSurvivesRollback(AccountOnlineSynchronizationCommon):
    def _roll_back_the_callers_transaction(self):
        self.env.cr.clear()
        with self.sync_env_with_side_cursors():
            self.env.cr.postrollback.run()

    def test_a_reported_error_outlives_the_raise(self):
        link = self.account_online_link
        link.state = "connected"
        self.account_online_account.fetching_status = "processing"
        messages_before = len(link.message_ids)

        with self.assertRaises(UserError):
            link._log_information(
                state="error",
                subject="Error",
                message="The bank refused the request.",
                raise_error=True,
            )

        self.env.invalidate_all()
        self.assertEqual(link.state, "connected")
        self.assertEqual(len(link.message_ids), messages_before)

        self._roll_back_the_callers_transaction()

        self.env.invalidate_all()
        self.assertEqual(link.state, "error")
        self.assertEqual(self.account_online_account.fetching_status, "done")
        self.assertEqual(len(link.message_ids), messages_before + 1)

    def test_renewed_tokens_outlive_a_later_failure(self):
        link = self.account_online_link
        tokens = {"refresh_token": "renewed-refresh", "access_token": "renewed-access"}

        with self.assertRaises(UserError):
            link._store_tokens(tokens)
            link._replay_on_rollback("_store_tokens", tokens)
            raise UserError("the next call failed")

        self.env.invalidate_all()
        self.assertNotEqual(link.sudo().refresh_token, "renewed-refresh")

        self._roll_back_the_callers_transaction()

        self.env.invalidate_all()
        self.assertEqual(link.sudo().refresh_token, "renewed-refresh")
        self.assertEqual(link.sudo().access_token, "renewed-access")

    def test_a_consumed_redirect_warning_stays_consumed(self):
        link = self.account_online_link
        link._set_connection_state_details(
            self.euro_bank_journal,
            {
                "status": "error",
                "error_type": "redirect_warning",
                "error_message": "Reconnect your bank",
                "action": {"type": "ir.actions.act_url", "url": "https://example.com"},
            },
        )

        with self.assertRaises(RedirectWarning):
            self.euro_bank_journal.action_view_dashboard_asynchronous_action()

        self.env.invalidate_all()
        self.assertTrue(link._get_connection_state_details(self.euro_bank_journal))

        self._roll_back_the_callers_transaction()

        self.env.invalidate_all()
        self.assertFalse(link._get_connection_state_details(self.euro_bank_journal))
