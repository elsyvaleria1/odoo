from odoo.tests import TransactionCase, tagged

SYNC_DOMAIN = [
    ("microsoft_calendar_rtoken", "!=", False),
    ("microsoft_synchronization_stopped", "=", False),
]


@tagged("post_install", "-at_install")
class TestMicrosoftSyncCandidates(TransactionCase):
    """Who the synchronisation cron picks up, and why it cannot ask SQL.

    The refresh token rests in `credential.credential`'s encrypted JSON, so
    `res.users.microsoft_calendar_rtoken` is a compute, and the stop flag is a
    related through `res_users_settings_id`, which has no column. The cron
    searched res.users on both and died with `Cannot convert
    res.users.microsoft_calendar_rtoken to SQL because it is not stored` on
    every run, whether or not anybody had connected a calendar.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {"name": "Sync Candidate", "login": "microsoft_sync_candidate"}
        )

    def _candidates(self):
        return self.env["res.users"]._microsoft_sync_candidates()

    def test_the_cron_runs_when_nobody_has_connected(self):
        self.assertNotIn(self.user, self._candidates())

        self.env["res.users"]._sync_all_microsoft_calendar()

    def test_a_connected_user_is_picked_up(self):
        self.user._set_microsoft_auth_tokens("an-access", "a-refresh", 3600)

        self.assertIn(self.user, self._candidates())

    def test_a_user_who_stopped_syncing_is_left_out(self):
        self.user._set_microsoft_auth_tokens("an-access", "a-refresh", 3600)
        self.user.sudo().microsoft_synchronization_stopped = True

        self.assertNotIn(self.user, self._candidates())

    def test_a_user_who_never_connected_is_left_out(self):
        self.assertFalse(self.user.sudo().microsoft_calendar_credential_id)

        self.assertNotIn(self.user, self._candidates())

    def test_a_credential_without_a_refresh_token_falls_out_in_python(self):
        """The SQL half is deliberately a superset: it sees the link to the
        credential, not what is inside it."""
        self.user._set_microsoft_auth_tokens("access-only", False, 3600)
        candidates = (
            self.env["res.users"]
            .sudo()
            .search([("microsoft_calendar_credential_id", "!=", False)])
        )

        self.assertIn(self.user, candidates)
        self.assertNotIn(self.user, self._candidates())
        self.assertNotIn(self.user, candidates.filtered_domain(SYNC_DOMAIN))
