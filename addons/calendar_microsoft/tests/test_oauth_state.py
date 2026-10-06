from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.calendar_microsoft.utils.calendar_microsoft import CALENDAR_SCOPE
from odoo.addons.integration.controllers.oauth import OAuthController
from odoo.addons.integration_microsoft.models.integration_service import (
    LEGACY_CALLBACK_PATH,
)


@tagged("post_install", "-at_install")
class TestMicrosoftCalendarAuthorization(HttpCase):
    """A calendar authorizes the user's own connection to Microsoft through the
    one OAuth flow, answering at the path Entra registrations already list."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env.ref("integration_microsoft.service_microsoft")
        cls.service._set_oauth_client("client-id", "client-secret", company=False)
        cls.service.oauth_redirect_path = LEGACY_CALLBACK_PATH
        cls.user = new_test_user(cls.env, login="mscal_oauth", groups="base.group_user")

    def test_the_sync_route_authorizes_the_users_own_connection_once(self):
        self.authenticate("mscal_oauth", "mscal_oauth")
        answer = self.call_jsonrpc(
            "/calendar_sync/microsoft/sync_data",
            {"model": "calendar.event", "fromurl": "/odoo/calendar"},
        )
        self.assertEqual(answer["status"], "need_auth")
        connection = self.env["integration.connection"]._find_personal(
            self.service, self.user
        )
        self.assertTrue(
            answer["url"].startswith(f"/integration/oauth/authorize/{connection.id}?")
        )

        to_microsoft = self.url_open(answer["url"], allow_redirects=False)
        self.assertEqual(to_microsoft.status_code, 303, to_microsoft.text)
        consent = urlsplit(to_microsoft.headers["Location"])
        params = parse_qs(consent.query)
        self.assertEqual(consent.netloc, "login.microsoftonline.com")
        self.assertEqual(params["client_id"], ["client-id"])
        self.assertEqual(params["scope"], [CALENDAR_SCOPE])
        self.assertTrue(params["redirect_uri"][0].endswith(LEGACY_CALLBACK_PATH))

        query = urlencode({"state": params["state"][0], "code": "a code"})
        tokens = {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
        }
        with patch.object(
            OAuthController, "_exchange_code_for_tokens", return_value=tokens
        ) as exchange:
            accepted = self.url_open(
                f"{LEGACY_CALLBACK_PATH}?{query}", allow_redirects=False
            )
            self.url_open(f"{LEGACY_CALLBACK_PATH}?{query}", allow_redirects=False)
        self.assertEqual(accepted.status_code, 303, accepted.text)
        self.assertTrue(accepted.headers["Location"].endswith("/odoo/calendar"))
        exchange.assert_called_once()
        self.assertEqual(self.user._calendar_sync_connection("microsoft"), connection)
        self.assertTrue(connection.oauth_redirect_uri.endswith(LEGACY_CALLBACK_PATH))

    def test_without_a_client_the_admin_is_asked_first(self):
        self.service._oauth_app_connection().active = False
        self.authenticate("mscal_oauth", "mscal_oauth")
        answer = self.call_jsonrpc(
            "/calendar_sync/microsoft/sync_data", {"model": "calendar.event"}
        )
        self.assertEqual(answer["status"], "need_config_from_admin")
