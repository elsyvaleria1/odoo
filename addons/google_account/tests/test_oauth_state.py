import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode

import odoo.http
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import hash_sign, issue_session_state, security

from odoo.addons.google_account.controllers import main


@tagged("post_install", "-at_install")
class TestGoogleOAuthState(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login="google_oauth", groups="base.group_user"
        )
        cls.other = new_test_user(
            cls.env, login="google_oauth_other", groups="base.group_user"
        )

    def setUp(self):
        super().setUp()
        self.authenticate("google_oauth", "google_oauth")

    def _issue(self, user=None, from_url="/odoo/calendar"):
        session = odoo.http.root.session_store.get(self.session.sid)
        state = issue_session_state(
            self.env(user=user or self.user),
            main.OAUTH_STATE_SCOPE,
            session,
            {"s": "calendar", "f": from_url},
            max_age_seconds=main._OAUTH_STATE_MAX_AGE_SECONDS,
        )
        odoo.http.root.session_store.save(session)
        return state

    def _callback(self, state, **params):
        params = {"state": state, "code": "attacker-or-user-code", **params}
        with (
            patch.object(
                type(self.env["google.service"]),
                "_get_google_tokens",
                return_value=("access", "refresh", 3600),
            ) as exchange,
            patch.object(
                type(self.env["res.users.settings"]),
                "_set_google_auth_tokens",
                create=True,
            ) as store,
        ):
            response = self.url_open(
                f"/google_account/authentication?{urlencode(params)}",
                allow_redirects=False,
            )
        return response, exchange, store

    def _assert_refused(self, state):
        response, exchange, store = self._callback(state)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("invalid, expired or already used", response.text)
        exchange.assert_not_called()
        store.assert_not_called()

    def test_the_issued_state_is_accepted_once(self):
        state = self._issue()
        response, exchange, store = self._callback(state)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(response.headers["Location"].endswith("/odoo/calendar"))
        exchange.assert_called_once()
        store.assert_called_once_with("access", "refresh", 3600)
        self._assert_refused(state)

    def test_a_provider_error_also_needs_the_issued_state(self):
        state = self._issue()
        response, exchange, _store = self._callback(state, code="", error="denied")
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=denied", response.headers["Location"])
        exchange.assert_not_called()
        self._assert_refused(state)

    def test_an_expired_state_is_refused(self):
        state = self._issue()
        later = SimpleNamespace(
            time=lambda: time.time() + main._OAUTH_STATE_MAX_AGE_SECONDS + 1
        )
        with patch.object(security, "time", later):
            self._assert_refused(state)

    def test_a_tampered_or_unsigned_state_is_refused(self):
        state = self._issue()
        forged = hash_sign(
            self.env,
            main.OAUTH_STATE_SCOPE,
            {"s": "calendar", "f": "https://evil.test", "nonce": "n"},
            1,
        )
        for presented in (
            state[:-2] + ("A" if state[-2] != "A" else "B") + state[-1],
            forged,
            '{"d": "db", "s": "calendar", "f": "/odoo/calendar"}',
            "",
        ):
            with self.subTest(presented=presented):
                self._issue()
                self._assert_refused(presented)

    def test_a_state_issued_in_another_session_or_to_another_user_is_refused(self):
        foreign = self._issue()
        self.authenticate("google_oauth", "google_oauth")
        self._issue()
        self._assert_refused(foreign)
        self.authenticate("google_oauth_other", "google_oauth_other")
        other_user = self._issue(user=self.user)
        self._assert_refused(other_user)
