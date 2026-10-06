from odoo.tests import HttpCase, tagged

from odoo.addons.integration_google.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)


@tagged("post_install", "-at_install")
class TestIntegrationGoogle(HttpCase):
    """Google is one OAuth service: users authorize their own connection to it,
    with the company's client, at a callback its consoles may still list under
    the module's old name."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env.ref("integration_google.service_google")

    def test_users_authorize_their_own_connection(self):
        self.assertEqual(self.service.auth_type, "oauth2")
        self.assertTrue(self.service.allow_user_credentials)
        self.assertEqual(
            self.service.oauth_redirect_path, "/integration/oauth/callback"
        )

    def test_the_old_callback_path_is_served_and_may_be_kept(self):
        self.assertEqual(LEGACY_CALLBACK_PATH, "/google_account/authentication")
        self.assertIn(LEGACY_CALLBACK_PATH, self.service._oauth_callback_paths())
        self.service.oauth_redirect_path = LEGACY_CALLBACK_PATH

        self.authenticate("admin", "admin")
        answer = self.url_open(f"{LEGACY_CALLBACK_PATH}?state=forged&code=a-code")

        self.assertEqual(answer.status_code, 200)
        self.assertIn("authorization state is invalid", answer.text)

    def test_the_settings_keep_the_client_in_the_vault(self):
        self.env["res.config.settings"].create(
            {
                "google_oauth_client_id": "settings-client",
                "google_oauth_client_secret": "settings-secret",
            }
        ).execute()

        self.assertTrue(self.service._has_oauth_client())
        self.assertEqual(
            self.service._oauth_app_connection()._oauth_client(),
            ("settings-client", "settings-secret"),
        )
        values = self.env["res.config.settings"].default_get(
            ["google_oauth_client_id", "google_oauth_client_secret"]
        )
        self.assertEqual(values.get("google_oauth_client_id"), "settings-client")
        self.assertFalse(values.get("google_oauth_client_secret"))

    def test_google_issues_a_refresh_token_and_keeps_earlier_scopes(self):
        self.assertEqual(
            self.service._oauth_authorize_extra(),
            {
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
            },
        )
