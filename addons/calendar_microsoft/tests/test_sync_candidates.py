from odoo.tests import TransactionCase, tagged

from odoo.addons.calendar_microsoft.tests.common import authorize_microsoft_calendar


@tagged("post_install", "-at_install")
class TestMicrosoftSyncCandidates(TransactionCase):
    """Who the synchronisation cron picks up: the users whose Microsoft connection
    is authorized, found in SQL on the connections, less the stopped ones."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {"name": "Sync Candidate", "login": "microsoft_sync_candidate"}
        )

    def _candidates(self):
        return self.env["res.users"]._calendar_sync_candidates("microsoft")

    def test_the_cron_runs_when_nobody_has_connected(self):
        self.assertNotIn(self.user, self._candidates())

        self.env["calendar.sync.account"]._cron_sync()

    def test_an_authorized_user_is_picked_up(self):
        authorize_microsoft_calendar(self.user)

        self.assertIn(self.user, self._candidates())

    def test_a_user_who_never_authorized_is_left_out(self):
        self.env["integration.connection"]._personal(
            self.env.ref("integration_microsoft.service_microsoft"), self.user
        )

        self.assertNotIn(self.user, self._candidates())

    def test_a_revoked_grant_is_left_out_until_authorized_again(self):
        authorize_microsoft_calendar(self.user).needs_reauthorization = True

        self.assertNotIn(self.user, self._candidates())
        self.assertFalse(self.user._calendar_sync_connection("microsoft"))

    def test_a_user_who_stopped_syncing_is_not_synced(self):
        authorize_microsoft_calendar(self.user)
        self.user._calendar_sync_account("microsoft").stopped = True

        self.assertEqual(self.user._calendar_sync_status("microsoft"), "sync_stopped")

    def test_a_user_who_stopped_syncing_is_left_out(self):
        authorize_microsoft_calendar(self.user)
        self.user.calendar_sync_stop("microsoft")

        self.assertNotIn(self.user, self._candidates())
