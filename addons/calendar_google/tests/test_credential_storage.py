from unittest.mock import MagicMock, patch

from odoo.libs.guarded_http import GuardedSession
from odoo.tests import TransactionCase, tagged

from odoo.addons.calendar_google.tests.common import authorize_google_calendar
from odoo.addons.calendar_google.utils.calendar_google import GoogleCalendarService
from odoo.addons.integration.tests.common import revealed


@tagged("post_install", "-at_install")
class TestGoogleCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = cls.env["res.users"].create(
            {"name": "Google User", "login": "google_user_probe"}
        )

    def test_the_tokens_rest_on_the_users_connection(self):
        connection = authorize_google_calendar(self.user, "an-access", "a-refresh")

        credential = connection.credential_id.sudo()
        self.assertEqual(credential.owner_user_id, self.user)
        self.assertEqual(credential.oauth_access_token, "an-access")
        self.assertEqual(credential.oauth_refresh_token, "a-refresh")
        self.assertEqual(self.user._calendar_sync_connection("google"), connection)

    def test_no_token_field_or_column_is_left_on_the_settings(self):
        Settings = self.env["res.users.settings"]
        for name in (
            "google_calendar_token",
            "google_calendar_rtoken",
            "google_calendar_token_validity",
            "google_calendar_credential_id",
        ):
            self.assertNotIn(name, Settings._fields)
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'res_users_settings'
               AND column_name IN (
                   'google_calendar_token', 'google_calendar_rtoken',
                   'google_calendar_token_validity', 'google_calendar_credential_id'
               )
            """
        )
        self.assertEqual(self.env.cr.fetchall(), [])

    def test_resetting_the_account_forgets_the_authorization(self):
        connection = authorize_google_calendar(self.user)
        credential = connection.credential_id

        self.env["wizard.calendar.sync.reset"].create(
            {
                "provider": "google",
                "user_id": self.user.id,
                "delete_policy": "dont_delete",
            }
        ).reset_account()

        self.assertFalse(credential.exists())
        self.assertFalse(self.user._calendar_sync_connection("google"))

    def test_a_call_carries_the_connections_token_to_google(self):
        connection = authorize_google_calendar(self.user, "the-access")
        response = MagicMock(status_code=200, headers={}, content=b"{}")
        response.json.return_value = {"items": [], "nextSyncToken": "next"}

        with patch.object(GuardedSession, "request", return_value=response) as sent:
            _events, next_sync_token, _reminders = GoogleCalendarService(
                self.env
            ).get_events(sync_token="previous", connection=connection)

        self.assertEqual(next_sync_token, "next")
        call = sent.call_args.kwargs
        self.assertEqual(
            call["url"],
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        )
        self.assertEqual(call["params"], {"syncToken": "previous"})
        self.assertNotIn("access_token", call["params"])
        self.assertEqual(
            revealed(call["headers"]["Authorization"]), "Bearer the-access"
        )


@tagged("post_install", "-at_install")
class TestCalendarProviderWizardCredentials(TransactionCase):
    def test_the_setup_wizard_keeps_the_client_where_google_reads_it(self):
        wizard = self.env["wizard.ir.config_parameter.update.calendar.provider"].create(
            {
                "external_calendar_provider": "google",
                "cal_client_id": "wizard-client",
                "cal_client_secret": "wizard-secret",
            }
        )

        wizard.action_calendar_prepare_external_provider_sync()

        service = self.env.ref("integration_google.service_google")
        self.assertTrue(service._has_oauth_client())
        self.assertEqual(service._oauth_client_id(), "wizard-client")
        self.assertFalse(
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("google_calendar_client_id")
        )
        self.assertEqual(
            self.env["wizard.ir.config_parameter.update.calendar.provider"].default_get(
                ["cal_client_id", "cal_client_secret"]
            ),
            {"cal_client_id": "wizard-client"},
            "the secret is written, never read back into a form",
        )
