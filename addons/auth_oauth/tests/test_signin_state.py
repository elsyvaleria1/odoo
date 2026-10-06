import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import hash_sign, mute_logger, security

from odoo.addons.auth_oauth.controllers import main


@tagged("post_install", "-at_install")
class TestSigninState(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider = cls.env.ref("auth_oauth.provider_google")
        cls.provider.write({"enabled": True, "client_id": "google-client-id"})
        cls.user = new_test_user(cls.env, "oauth_signin")
        cls.user.write(
            {"oauth_provider_id": cls.provider.id, "oauth_uid": "signin-uid"}
        )

    def _authorize(self, **params):
        query = f"?{urlencode(params)}" if params else ""
        response = self.url_open(
            f"/auth_oauth/authorize/{self.provider.id}{query}", allow_redirects=False
        )
        self.assertEqual(response.status_code, 303, response.text)
        location = urlsplit(response.headers["Location"])
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}",
            self.provider.auth_endpoint,
        )
        return parse_qs(location.query)["state"][0]

    def _signin(self, state):
        with (
            patch.object(
                type(self.env["res.users"]),
                "_get_oauth_identity",
                return_value={"user_id": "signin-uid"},
            ),
            mute_logger("odoo.addons.auth_oauth.controllers.main"),
        ):
            return self.url_open(
                "/auth_oauth/signin?"
                + urlencode({"access_token": "provider-token", "state": state}),
                allow_redirects=False,
            )

    def _assert_signed_in(self, response, landing):
        self.assertEqual(response.status_code, 303, response.text)
        self.assertNotIn("oauth_error", response.headers["Location"])
        self.assertTrue(
            response.headers["Location"].endswith(landing), response.headers["Location"]
        )
        self.assertEqual(
            self.call_jsonrpc("/web/session/get_session_info")["uid"], self.user.id
        )

    def _assert_refused(self, response):
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(
            response.headers["Location"].endswith("/web/login?oauth_error=2"),
            response.headers["Location"],
        )

    def test_the_login_page_links_to_the_authorize_route(self):
        response = self.url_open("/web/login?redirect=/odoo/discuss")
        self.assertIn(
            f"/auth_oauth/authorize/{self.provider.id}?redirect=%2Fodoo%2Fdiscuss",
            response.text,
        )

    def test_the_state_signs_in_once(self):
        state = self._authorize(redirect="/odoo/discuss")
        self.assertEqual(json_loads(state)["d"], self.env.cr.dbname)
        self._assert_signed_in(self._signin(state), "/odoo/discuss")
        self._assert_refused(self._signin(state))

    def test_without_a_landing_page_an_employee_lands_on_the_backend(self):
        self._assert_signed_in(self._signin(self._authorize()), "/odoo")

    def test_an_expired_state_is_refused(self):
        state = self._authorize()
        later = SimpleNamespace(
            time=lambda: time.time() + main._LOGIN_STATE_MAX_AGE_SECONDS + 1
        )
        with patch.object(security, "time", later):
            self._assert_refused(self._signin(state))

    def test_a_state_the_server_did_not_issue_is_refused(self):
        state = json_loads(self._authorize())
        token = state["token"]
        unsigned = {
            "d": self.env.cr.dbname,
            "p": self.provider.id,
            "r": "/odoo",
        }
        forged = {
            **state,
            "token": hash_sign(
                self.env,
                main.LOGIN_STATE_SCOPE,
                {"p": self.provider.id, "db": self.env.cr.dbname, "nonce": "n"},
                1,
            ),
        }
        flipped = {
            **state,
            "token": token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1],
        }
        for tampered in (unsigned, forged, flipped, {**state, "token": None}):
            with self.subTest(tampered=tampered):
                self._authorize()
                self._assert_refused(self._signin(json_dumps(tampered)))

    def test_a_state_issued_to_another_browser_session_is_refused(self):
        state = self._authorize()
        self.opener.cookies.clear()
        self._authorize()
        self._assert_refused(self._signin(state))
        self.opener.cookies.clear()
        self._assert_refused(self._signin(state))

    def test_the_odoo_account_entry_signs_in_without_a_state(self):
        self.user.oauth_provider_id = self.env.ref("auth_oauth.provider_odoo")
        with patch.object(
            type(self.env["res.users"]),
            "_get_oauth_identity",
            return_value={"user_id": "signin-uid"},
        ):
            response = self.url_open(
                "/auth_oauth/oea?access_token=odoo-token", allow_redirects=False
            )
        self._assert_signed_in(response, "/odoo")
