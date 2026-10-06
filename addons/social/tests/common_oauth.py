import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo.tests import new_test_user
from odoo.tools import hash_sign, mute_logger, security

from odoo.addons.social.models.social_media import (
    OAUTH_STATE_MAX_AGE_SECONDS,
    OAUTH_STATE_SCOPE,
)


class SocialOAuthStateMixin:
    """The account callback of one media flow accepts the state the session it
    started in issued, once; mixed into an HttpCase per flow.

    A flow sets ``MEDIA_XMLID``, ``CALLBACK``, ``CARRIED`` (whether the provider
    brings the state back) and ``OWN_APP`` (whether the database has its own
    app credentials, else IAP), and implements ``_callback_params`` and
    ``_patch_accounts_creation``."""

    allow_inherited_tests_method = True
    MEDIA_XMLID = None
    CALLBACK = None
    CARRIED = True
    OWN_APP = True
    EGRESS_RESPONSE = SimpleNamespace(
        text="https://iap.test/add_accounts", status_code=200
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media = cls.env.ref(cls.MEDIA_XMLID)
        cls.manager = new_test_user(
            cls.env,
            login="oauth_social_manager",
            groups="base.group_user,social.group_social_manager",
        )

    def setUp(self):
        super().setUp()
        self.authenticate("oauth_social_manager", "oauth_social_manager")

    def _callback_params(self):
        raise NotImplementedError

    def _patch_accounts_creation(self):
        raise NotImplementedError

    def _start(self, media=None):
        secret = "app-secret" if self.OWN_APP else False
        with (
            patch.object(
                type(self.env["credential.credential"]),
                "_get_system_secret",
                return_value=secret,
            ),
            patch.object(
                type(self.env["ir.egress"]),
                "request",
                return_value=self.EGRESS_RESPONSE,
            ) as egress,
        ):
            action = self.call_jsonrpc(
                "/web/dataset/call_button",
                {
                    "model": "social.media",
                    "method": "action_add_account",
                    "args": [(media or self.media).ids],
                    "kwargs": {},
                },
            )
        if not self.CARRIED or media:
            return None
        return self._state_of(action, egress)

    def _state_of(self, action, egress):
        return parse_qs(urlsplit(action["url"]).query)["state"][0]

    def _callback(self, state=None):
        params = self._callback_params()
        if state is not None:
            params["state"] = state
        with mute_logger("odoo.http"):
            return self.url_open(
                f"{self.CALLBACK}?{urlencode(params)}", allow_redirects=False
            )

    def _assert_accepted(self, state):
        with self._patch_accounts_creation() as create:
            response = self._callback(state)
        self.assertEqual(response.status_code, 303, response.text)
        create.assert_called_once()

    def _assert_refused(self, state):
        with self._patch_accounts_creation() as create:
            response = self._callback(state)
        self.assertEqual(response.status_code, 403, response.text)
        self.assertIn("authentication issue", response.text)
        create.assert_not_called()

    def test_the_state_is_accepted_once(self):
        state = self._start()
        self._assert_accepted(state)
        self._assert_refused(state)

    def test_an_expired_state_is_refused(self):
        state = self._start()
        later = SimpleNamespace(
            time=lambda: time.time() + OAUTH_STATE_MAX_AGE_SECONDS + 1
        )
        with patch.object(security, "time", later):
            self._assert_refused(state)

    def test_a_tampered_state_is_refused(self):
        forged = hash_sign(
            self.env,
            OAUTH_STATE_SCOPE,
            {
                "media_id": self.media.id,
                "db": self.env.cr.dbname,
                "uid": self.manager.id,
                "nonce": "n",
            },
            1,
        )
        for tampered in ("not a state", forged):
            with self.subTest(tampered=tampered):
                self._start()
                self._assert_refused(tampered)
        state = self._start()
        if state:
            self._assert_refused(
                state[:-2] + ("A" if state[-2] != "A" else "B") + state[-1]
            )

    def test_a_state_from_another_session_is_refused(self):
        state = self._start()
        self.authenticate("oauth_social_manager", "oauth_social_manager")
        self._assert_refused(state)

    def test_a_state_issued_for_another_media_is_refused(self):
        other = self.env["social.media"].create({"name": "Other media"})

        issued = []

        def issue(media):
            issued.append(media._issue_oauth_state(carried=self.CARRIED))
            return {"type": "ir.actions.act_url", "url": "/"}

        with patch.object(type(other), "_action_add_account", issue):
            self._start(other)
        self._assert_refused(issued[0] if self.CARRIED else None)
