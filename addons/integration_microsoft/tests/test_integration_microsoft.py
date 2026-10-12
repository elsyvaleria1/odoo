from odoo.tests import HttpCase, tagged

from odoo.addons.integration_microsoft.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)


@tagged("post_install", "-at_install")
class TestIntegrationMicrosoft(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env.ref("integration_microsoft.service_microsoft")

    def test_users_authorize_their_own_connection(self):
        self.assertEqual(self.service.auth_type, "oauth2")
        self.assertTrue(self.service.allow_user_credentials)
        self.assertEqual(
            self.service.oauth_redirect_path, "/integration/oauth/callback"
        )

    def test_the_old_callback_path_is_served_and_may_be_kept(self):
        self.assertEqual(LEGACY_CALLBACK_PATH, "/microsoft_account/authentication")
        self.assertIn(LEGACY_CALLBACK_PATH, self.service._oauth_callback_paths())
        self.service.oauth_redirect_path = LEGACY_CALLBACK_PATH

        self.authenticate("admin", "admin")
        answer = self.url_open(f"{LEGACY_CALLBACK_PATH}?state=forged&code=a-code")

        self.assertEqual(answer.status_code, 200)
        self.assertIn("authorization state is invalid", answer.text)

    def test_the_settings_keep_the_client_in_the_vault(self):
        self.env["res.config.settings"].create(
            {
                "microsoft_oauth_client_id": "settings-client",
                "microsoft_oauth_client_secret": "settings-secret",
            }
        ).execute()

        self.assertTrue(self.service._has_oauth_client())
        self.assertEqual(
            self.service._oauth_app_connection()._oauth_client(),
            ("settings-client", "settings-secret"),
        )
        values = self.env["res.config.settings"].default_get(
            ["microsoft_oauth_client_id", "microsoft_oauth_client_secret"]
        )
        self.assertEqual(values.get("microsoft_oauth_client_id"), "settings-client")
        self.assertFalse(values.get("microsoft_oauth_client_secret"))

    def test_microsoft_wants_the_scope_with_every_token_request(self):
        self.assertTrue(self.service.oauth_token_sends_scope)
