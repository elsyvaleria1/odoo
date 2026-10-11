import base64
from datetime import timedelta
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo import fields
from odoo.exceptions import UserError
from odoo.libs.guarded_http import GuardedSession
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, new_test_user
from odoo.tools import mute_logger

from odoo.addons.integration.controllers.oauth import OAuthController


def id_token(**claims) -> str:
    payload = base64.urlsafe_b64encode(json_dumps(claims).encode()).decode()
    return f"header.{payload.rstrip('=')}.signature"


class OAuthMailServerCase(HttpCase):

    allow_inherited_tests_method = True
    service_xmlid = None
    authorize_method = None
    legacy_path = None
    type_field = "smtp_authentication"
    type_value = None
    server_values = None
    scope_words = ()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env.ref(cls.service_xmlid)
        cls.service._set_oauth_client("CLIENT-ID", "CLIENT-SECRET", company=False)
        cls.server = cls._create_server("shared@example.com")
        cls.owner = new_test_user(
            cls.env,
            login="mail_owner",
            email="owner@example.com",
            groups="base.group_user",
        )
        cls.personal = cls._create_server(
            "owner@example.com", owner_user_id=cls.owner.id
        )

    @classmethod
    def _create_server(cls, address, **values):
        return cls.env["ir.mail_server"].create(
            {
                "name": address,
                "smtp_user": address,
                "from_filter": address,
                "active": False,
                cls.type_field: cls.type_value,
                **cls.server_values,
                **values,
            }
        )

    def _authorize_url(self, server, user=None):
        server = server.with_user(user or self.env.user).sudo()
        return getattr(server, self.authorize_method)()["url"]

    def _consent(self, server, login="admin"):
        self.authenticate(login, login)
        user = self.env["res.users"].search([("login", "=", login)])
        response = self.url_open(
            self._authorize_url(server, user), allow_redirects=False
        )
        self.assertEqual(response.status_code, 303, response.text)
        return parse_qs(urlsplit(response.headers["Location"]).query)

    def _callback(self, state, tokens, path=None):
        query = urlencode({"state": state, "code": "a-code"})
        with patch.object(
            OAuthController, "_exchange_code_for_tokens", return_value=tokens
        ) as exchange:
            response = self.url_open(
                f"{path or '/integration/oauth/callback'}?{query}",
                allow_redirects=False,
            )
        return response, exchange

    def _tokens(self, email):
        return {
            "access_token": "AT",
            "refresh_token": "RT",
            "expires_in": 3600,
            "id_token": id_token(email=email, email_verified=True),
        }

    def test_a_server_authorizes_its_own_connection_once(self):
        params = self._consent(self.server)
        connection = self.server._oauth2_connection()
        self.assertEqual(connection.service_id, self.service)
        self.assertEqual(connection.res_id, self.server.id)
        self.assertEqual(params["client_id"], ["CLIENT-ID"])
        for word in self.scope_words:
            self.assertIn(word, params["scope"][0].split())

        state = params["state"][0]
        response, exchange = self._callback(state, self._tokens("shared@example.com"))
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(
            response.headers["Location"].endswith(
                f"/odoo/ir.mail_server/{self.server.id}"
            )
        )
        self.server.invalidate_recordset()
        self.assertTrue(self.server.active)
        self.assertTrue(self.server.oauth2_authorized)
        with mute_logger("odoo.addons.integration.controllers.oauth"):
            self._callback(state, self._tokens("shared@example.com"))
        exchange.assert_called_once()

    def test_without_a_client_the_admin_is_asked_to_configure_one(self):
        self.service._oauth_app_connection().credential_id.oauth_client_secret = False
        with self.assertRaises(UserError):
            self._authorize_url(self.server)

    def test_the_owner_authorizes_a_personal_server_with_its_own_account(self):
        params = self._consent(self.personal, login="mail_owner")
        response, _exchange = self._callback(
            params["state"][0], self._tokens("owner@example.com")
        )
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(
            response.headers["Location"].endswith(
                "/odoo/my-preferences/%s" % self.owner.id
            )
        )
        self.assertTrue(self.personal.oauth2_authorized)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_another_account_keeps_no_grant_on_a_personal_server(self):
        params = self._consent(self.personal, login="mail_owner")
        response, _exchange = self._callback(
            params["state"][0], self._tokens("someone.else@example.com")
        )
        self.assertIn("make sure your addresses match", response.text.lower())
        self.personal.invalidate_recordset()
        self.assertFalse(self.personal.active)
        self.assertFalse(self.personal._oauth2_connection().credential_id)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_nobody_else_authorizes_a_personal_server(self):
        new_test_user(self.env, login="mail_other", groups="base.group_user")
        self.authenticate("mail_other", "mail_other")
        response = self.url_open(
            self._authorize_url(self.personal), allow_redirects=False
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("not allowed to authorize", response.text)

    def test_the_login_carries_a_current_token(self):
        connection = self.env["integration.connection"]._bound(
            self.server, self.service, " ".join(self.scope_words)
        )
        connection._oauth_store_tokens(self._tokens("shared@example.com"), "")
        self.assertIn(
            "auth=Bearer AT",
            self.server._oauth2_generate_string(None, "shared@example.com"),
        )

        connection.credential_id.sudo().oauth_token_date_expiration = (
            fields.Datetime.now() - timedelta(minutes=5)
        )
        refreshed = MagicMock(ok=True)
        refreshed.json.return_value = {"access_token": "FRESH", "expires_in": 3600}
        with patch.object(GuardedSession, "request", return_value=refreshed) as sent:
            login = self.server._oauth2_generate_string(None, "shared@example.com")
        self.assertIn("auth=Bearer FRESH", login)
        self.assertEqual(sent.call_args.args[1], self.service.oauth_token_endpoint)

    def test_a_server_that_stops_using_the_vendor_forgets_its_grant(self):
        connection = self.env["integration.connection"]._bound(
            self.server, self.service
        )
        connection._oauth_store_tokens(self._tokens("shared@example.com"), "")
        credential = connection.credential_id

        self.server.write({self.type_field: "login", "smtp_encryption": "none"})

        self.assertFalse(credential.exists())

    def test_a_deleted_server_takes_its_connection_with_it(self):
        connection = self.env["integration.connection"]._bound(
            self.server, self.service
        )
        connection._oauth_store_tokens(self._tokens("shared@example.com"), "")
        credential = connection.credential_id

        self.server.unlink()

        self.assertFalse(connection.exists())
        self.assertFalse(credential.exists())

    def test_the_callback_registered_before_still_answers(self):
        self.service.oauth_redirect_path = self.legacy_path
        params = self._consent(self.server)
        self.assertTrue(params["redirect_uri"][0].endswith(self.legacy_path))
        response, _exchange = self._callback(
            params["state"][0],
            self._tokens("shared@example.com"),
            path=self.legacy_path,
        )
        self.assertEqual(response.status_code, 303, response.text)
