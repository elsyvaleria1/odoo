import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

from odoo.libs.guarded_http import GuardedSession
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase
from odoo.tools import hash_sign, mute_logger, security

from odoo.addons.mail_oauth2.models.mixin_oauth2_mail_provider import (
    OAUTH2_STATE_MAX_AGE_SECONDS,
)


class OAuth2StateFlowCase(HttpCase):
    provider = None
    open_method = None
    refresh_token_method = None
    controller_logger = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server, cls.other_server = cls.env["ir.mail_server"].create(
            [
                {
                    "name": name,
                    "smtp_host": "smtp.example.com",
                    "smtp_user": f"{name}@example.com",
                    "active": False,
                }
                for name in ("linked", "other")
            ]
        )

    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")

    def _configure_own_app(self):
        prefix = self.provider.prefix
        self.env["ir.config_parameter"].sudo().set_param(
            f"{prefix}_client_id", "CLIENT-ID"
        )
        self.env["credential.credential"]._set_system_secret(
            f"{prefix}_client_secret", "CLIENT-SECRET"
        )

    def _open(self, server):
        action = self.call_jsonrpc(
            "/web/dataset/call_button",
            {
                "model": "ir.mail_server",
                "method": self.open_method,
                "args": [server.ids],
                "kwargs": {},
            },
        )
        return action["url"]

    def _own_app_state(self, server):
        self._configure_own_app()
        return parse_qs(urlsplit(self._open(server)).query)["state"][0]

    def _confirm(self, state):
        query = urlencode({"code": "CODE", "state": state})
        with patch.object(
            self.registry["ir.mail_server"],
            self.refresh_token_method,
            return_value=("RT", "AT", int(time.time()) + 3600),
        ) as exchange:
            response = self.url_open(
                f"/{self.provider.route}/confirm?{query}", allow_redirects=False
            )
        return response, exchange

    def _iap_callback_path(self, server):
        self.env["ir.config_parameter"].sudo().set_param(
            f"{self.provider.prefix}_client_id", False
        )
        response = MagicMock(ok=True, status_code=200)
        response.json.return_value = {"url": "https://iap.test/consent"}
        with patch.object(GuardedSession, "request", return_value=response) as iap:
            self.assertEqual(self._open(server), "https://iap.test/consent")
        callback_url = urlsplit(iap.call_args.kwargs["params"]["callback_url"])
        self.assertEqual(set(parse_qs(callback_url.query)), {"state"})
        return f"{callback_url.path}?{callback_url.query}"

    def _iap_confirm(self, path):
        tokens = urlencode(
            {"access_token": "AT", "refresh_token": "RT", "expiration": "1"}
        )
        return self.url_open(f"{path}&{tokens}", allow_redirects=False)

    def _assert_linked(self, response, server):
        self.assertEqual(response.status_code, 303, response.text)
        server.invalidate_recordset()
        self.assertTrue(server.active)
        self.assertEqual(server[self.provider.field("refresh_token")], "RT")

    def _assert_refused(self, response, *servers):
        self.assertEqual(response.status_code, 403, response.text)
        for server in servers or (self.server, self.other_server):
            server.invalidate_recordset()
            self.assertFalse(server[self.provider.field("refresh_token")])

    def test_the_own_app_state_is_accepted_once_for_its_record(self):
        state = self._own_app_state(self.server)
        response, exchange = self._confirm(state)
        self._assert_linked(response, self.server)
        exchange.assert_called_once()
        self.assertFalse(self.other_server[self.provider.field("refresh_token")])
        with mute_logger(self.controller_logger):
            replayed, exchange = self._confirm(state)
        self.assertEqual(replayed.status_code, 403)
        exchange.assert_not_called()

    def test_the_iap_callback_is_accepted_once_for_its_record(self):
        path = self._iap_callback_path(self.server)
        self._assert_linked(self._iap_confirm(path), self.server)
        self.server[self.provider.field("refresh_token")] = False
        with mute_logger(self.controller_logger):
            self._assert_refused(self._iap_confirm(path))

    def test_an_expired_state_is_refused(self):
        later = SimpleNamespace(
            time=lambda: time.time() + OAUTH2_STATE_MAX_AGE_SECONDS + 1
        )
        state = self._own_app_state(self.server)
        with patch.object(security, "time", later), mute_logger(self.controller_logger):
            self._assert_refused(self._confirm(state)[0])
        path = self._iap_callback_path(self.server)
        with patch.object(security, "time", later), mute_logger(self.controller_logger):
            self._assert_refused(self._iap_confirm(path))

    def test_a_tampered_or_static_state_is_refused(self):
        state = self._own_app_state(self.server)
        claims = {
            "model": "ir.mail_server",
            "id": self.other_server.id,
            "db": self.env.cr.dbname,
            "uid": self.env.ref("base.user_admin").id,
            "nonce": "n",
        }
        static = security.hmac(
            self.env, self.provider.csrf_scope, ("ir.mail_server", self.server.id)
        )
        for tampered in (
            state[:-2] + ("A" if state[-2] != "A" else "B") + state[-1],
            hash_sign(self.env, self.provider.csrf_scope, claims, 1),
            json_dumps(
                {"model": "ir.mail_server", "id": self.server.id, "csrf_token": static}
            ),
            "",
        ):
            with self.subTest(tampered=tampered), mute_logger(self.controller_logger):
                self._own_app_state(self.server)
                self._assert_refused(self._confirm(tampered)[0])
        legacy = urlencode(
            {"model": "ir.mail_server", "rec_id": self.server.id, "csrf_token": static}
        )
        with mute_logger(self.controller_logger):
            self._assert_refused(
                self._iap_confirm(f"/{self.provider.route}/iap_confirm?{legacy}")
            )

    def test_a_state_issued_in_another_session_is_refused(self):
        foreign = self._own_app_state(self.other_server)
        self.authenticate("admin", "admin")
        self._own_app_state(self.server)
        with mute_logger(self.controller_logger):
            self._assert_refused(self._confirm(foreign)[0])
