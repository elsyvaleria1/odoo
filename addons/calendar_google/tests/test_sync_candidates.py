from odoo.tests import TransactionCase, tagged

from odoo.addons.calendar_google.tests.common import authorize_google_calendar


@tagged("post_install", "-at_install")
class TestGoogleSyncCandidates(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {"name": "Sync Candidate", "login": "google_sync_candidate"}
        )

    def _candidates(self):
        return self.env["res.users"]._calendar_sync_candidates("google")

    def test_the_cron_runs_when_nobody_has_connected(self):
        self.assertNotIn(self.user, self._candidates())

        self.env["calendar.sync.account"]._cron_sync()

    def test_an_authorized_user_is_picked_up(self):
        authorize_google_calendar(self.user)

        self.assertIn(self.user, self._candidates())

    def test_a_user_who_never_authorized_is_left_out(self):
        self.env["integration.connection"]._personal(
            self.env.ref("integration_google.service_google"), self.user
        )

        self.assertNotIn(self.user, self._candidates())

    def test_a_revoked_grant_is_left_out_until_authorized_again(self):
        authorize_google_calendar(self.user).needs_reauthorization = True

        self.assertNotIn(self.user, self._candidates())
        self.assertFalse(self.user._calendar_sync_connection("google"))

    def test_a_user_who_stopped_syncing_is_not_synced(self):
        authorize_google_calendar(self.user)
        self.user._calendar_sync_account("google").stopped = True

        self.assertEqual(self.user._calendar_sync_status("google"), "sync_stopped")

    def test_a_user_who_stopped_syncing_is_left_out(self):
        authorize_google_calendar(self.user)
        self.user.calendar_sync_stop("google")

        self.assertNotIn(self.user, self._candidates())
