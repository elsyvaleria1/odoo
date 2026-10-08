import time
from types import SimpleNamespace
from unittest.mock import patch

from odoo.fields import Command
from odoo.http._csrf import _get_csrf_digest, _get_csrf_secret
from odoo.tools import mute_logger, security

from odoo.addons.payment.models import payment_provider


class OnboardingStateCases:
    """The onboarding round trip of a provider whose return route exchanges an
    authorization code for credentials: mixed into a provider's
    `PaymentHttpCommon` test class, which sets `provider` and implements the
    hooks below."""

    allow_inherited_tests_method = True

    def _state_of_start_url(self, url) -> str:
        raise NotImplementedError

    def _return_query(self, state, provider_id) -> dict:
        raise NotImplementedError

    def _proxy_token_response(self) -> dict:
        raise NotImplementedError

    def _is_onboarded(self, provider) -> bool:
        raise NotImplementedError

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.onboarder = cls._create_new_internal_user(
            login="onboarder", groups="base.group_user,base.group_system"
        )

    def setUp(self):
        super().setUp()
        self.authenticate("admin", "admin")

    def _start(self) -> str:
        action = self.call_jsonrpc(
            "/web/dataset/call_kw/payment.provider/action_start_onboarding",
            {
                "model": "payment.provider",
                "method": "action_start_onboarding",
                "args": [self.provider.ids],
                "kwargs": {},
            },
        )
        return self._state_of_start_url(action["url"])

    def _return(self, query):
        Provider = type(self.env["payment.provider"])
        with (
            patch.object(
                Provider, "_send_api_request", return_value=self._proxy_token_response()
            ) as exchange,
            mute_logger("odoo.http", "odoo.addons.payment"),
        ):
            response = self.url_open(
                self.return_route, params=query, allow_redirects=False
            )
        return response, exchange

    def _assert_completed(self, query):
        response, exchange = self._return(query)
        self.assertEqual(response.status_code, 303, response.text)
        exchange.assert_called_once()
        self.provider.invalidate_recordset()
        self.assertTrue(self._is_onboarded(self.provider))

    def _assert_refused(self, query, provider=None):
        response, exchange = self._return(query)
        self.assertEqual(response.status_code, 403, response.text)
        exchange.assert_not_called()
        (provider or self.provider).invalidate_recordset()
        self.assertFalse(self._is_onboarded(provider or self.provider))

    def _session_csrf_token(self) -> str:
        max_ts = int(time.time() + 3600)
        digest = _get_csrf_digest(
            _get_csrf_secret(self.env), self.session.csrf_binding, max_ts
        )
        return f"{digest}o{max_ts}"

    def test_the_admin_onboarding_completes(self):
        state = self._start()
        self._assert_completed(self._return_query(state, self.provider.id))

    def test_a_replayed_state_is_refused(self):
        state = self._start()
        self._assert_completed(self._return_query(state, self.provider.id))
        self.provider.action_reset_credentials()
        self._assert_refused(self._return_query(state, self.provider.id))

    def test_an_expired_state_is_refused(self):
        state = self._start()
        later = SimpleNamespace(
            time=lambda: (
                time.time() + payment_provider.ONBOARDING_STATE_MAX_AGE_SECONDS + 1
            )
        )
        with patch.object(security, "time", later):
            self._assert_refused(self._return_query(state, self.provider.id))

    def test_a_provider_swapped_in_the_query_is_refused(self):
        other = self.provider.copy({"name": "Swapped"})
        state = self._start()
        self._assert_refused(self._return_query(state, other.id), provider=other)
        self.provider.invalidate_recordset()
        self.assertFalse(self._is_onboarded(self.provider))

    def test_a_user_without_the_provider_rights_is_refused(self):
        self.authenticate(self.internal_user.login, self.internal_user.login)
        own_token = self._session_csrf_token()
        query = self._return_query(own_token, self.provider.id)
        self._assert_refused({**query, "csrf_token": own_token})

    def test_a_user_who_lost_the_provider_rights_is_refused(self):
        self.authenticate(self.onboarder.login, self.onboarder.login)
        state = self._start()
        self.onboarder.group_ids = [
            Command.unlink(self.env.ref("base.group_system").id)
        ]
        self._assert_refused(self._return_query(state, self.provider.id))
