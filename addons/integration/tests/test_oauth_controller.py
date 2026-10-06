import base64
import hashlib
import hmac
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

from odoo.tests.common import HttpCase, TransactionCase, new_test_user
from odoo.tools import hash_sign, mute_logger, security

from odoo.addons.integration.controllers import oauth
from odoo.addons.integration.controllers.oauth import OAuthController


class TestOAuthTokenExchange(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["integration.service"].create(
            {
                "name": "OAuth Test Service",
                "code": "oauth_exchange_test",
                "endpoint_url": "https://api.oauth.test",
                "auth_type": "oauth2",
                "oauth_client_id": "app-client-id",
                "oauth_auth_endpoint": "https://oauth.test/authorize",
                "oauth_token_endpoint": "https://oauth.test/token",
            }
        )
        cls.category_oauth2 = cls.env.ref("credential.credential_category_oauth2")
        cls.controller = OAuthController()

    def _make_credential(self, **extra):
        values = {
            "name": "OAuth Exchange Credential",
            "category_id": self.category_oauth2.id,
            "endpoint_id": self.service.id,
            "company_id": self.env.company.id,
        }
        values.update(extra)
        return self.env["credential.credential"].create(values)

    def _exchange(self, credential):
        response = MagicMock()
        response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
        }
        response.raise_for_status.return_value = None
        with (
            patch.object(
                OAuthController,
                "_get_redirect_uri",
                return_value="https://odoo.test/api_gateway/oauth/callback",
            ),
            patch.object(requests.Session, "post", return_value=response) as mock_post,
        ):
            tokens = self.controller._exchange_code_for_tokens(credential, "auth-code")
        return tokens, mock_post

    def test_exchange_sends_secret_from_credential(self):
        credential = self._make_credential(oauth_client_secret="vault-s3cr3t")

        tokens, mock_post = self._exchange(credential)

        self.assertEqual(tokens["access_token"], "new-access-token")
        sent = mock_post.call_args.kwargs["data"]
        self.assertEqual(sent["client_secret"], "vault-s3cr3t")
        self.assertEqual(sent["client_id"], "app-client-id")
        self.assertEqual(sent["grant_type"], "authorization_code")

    def test_exchange_public_client_omits_secret(self):
        credential = self._make_credential(oauth_access_token="existing-token")

        _tokens, mock_post = self._exchange(credential)

        self.assertNotIn("client_secret", mock_post.call_args.kwargs["data"])


class TestOAuthClientIdResolution(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category_oauth2 = cls.env.ref("credential.credential_category_oauth2")

    def _setup(self, service_client_id, credential_client_id):
        slug = f"{'svc' if service_client_id else 'nosvc'}_"
        slug += "cred" if credential_client_id else "nocred"
        service = self.env["integration.service"].create(
            {
                "name": f"resolution {slug}",
                "code": f"oauth_res_{slug}",
                "endpoint_url": "https://api.oauth.test",
                "auth_type": "oauth2",
                "oauth_client_id": service_client_id or False,
                "oauth_auth_endpoint": "https://oauth.test/authorize",
                "oauth_token_endpoint": "https://oauth.test/token",
            }
        )
        return self.env["credential.credential"].create(
            {
                "name": f"resolution credential {slug}",
                "category_id": self.category_oauth2.id,
                "endpoint_id": service.id,
                "oauth_client_secret": "s3cr3t",
                "oauth_client_id": credential_client_id or False,
            }
        )

    def test_the_service_supplies_it(self):
        credential = self._setup("from-service", None)
        self.assertEqual(credential._oauth_client_id(), "from-service")

    def test_the_credential_supplies_it_when_the_service_does_not(self):
        credential = self._setup(None, "from-credential")
        self.assertEqual(
            credential._oauth_client_id(),
            "from-credential",
            "a client id entered on the credential form was ignored, and the flow "
            "then refused saying the service was not configured",
        )

    def test_the_service_still_wins(self):
        credential = self._setup("from-service", "from-credential")
        self.assertEqual(credential._oauth_client_id(), "from-service")

    def test_neither_resolves_to_nothing(self):
        credential = self._setup(None, None)
        self.assertFalse(
            credential._oauth_client_id(),
            "with neither configured the flow must still refuse, rather than "
            "authorize with an empty client id",
        )


class TestOAuthStateSigning(TransactionCase):
    def test_no_state_is_signed_without_a_database_secret(self):
        self.env["ir.config_parameter"].sudo().set_param("database.secret", "")
        fake_request = MagicMock(env=self.env, session={})
        with (
            patch.object(oauth, "request", fake_request),
            self.assertRaises(ValueError),
        ):
            OAuthController()._get_oauth_state(1)


_REFUSED = "The authorization state is invalid, expired or already used."


class TestOAuthCallbackState(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        new_test_user(
            cls.env, login="oauth_admin", groups="credential.group_credential_admin"
        )

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_state_that_is_no_signed_state_is_refused(self):
        self.authenticate("oauth_admin", "oauth_admin")
        for state in ('{"payload": {"nonce": "n"}, "sig": 42}', "é" * 64, "AQ"):
            with self.subTest(state=state):
                response = self.url_open(
                    f"{oauth._CALLBACK_PATH}?{urlencode({'state': state, 'code': 'c'})}"
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(_REFUSED, response.text)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_provider_refusal_is_answered_with_an_error_page(self):
        self.authenticate("oauth_admin", "oauth_admin")
        response = self.url_open(
            f"{oauth._CALLBACK_PATH}?{urlencode({'error': 'access_denied'})}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access_denied", response.text)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_an_authorization_of_a_missing_credential_is_answered_with_an_error_page(
        self,
    ):
        self.authenticate("oauth_admin", "oauth_admin")
        missing = self.env["credential.credential"].search([], order="id desc", limit=1)
        response = self.url_open(f"/api_transport/oauth/authorize/{missing.id + 1}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Credential not found", response.text)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_state_signed_with_the_bare_database_secret_is_refused(self):
        self.authenticate("oauth_admin", "oauth_admin")
        expiry = int(time.time()) + 600
        message = '{"credential_id":1,"nonce":"n"}'
        secret = self.env["ir.config_parameter"].sudo().get_param("database.secret")
        signature = hmac.new(
            secret.encode(), f"1:{message}:{expiry}".encode(), hashlib.sha256
        ).digest()
        state = base64.urlsafe_b64encode(
            b"\x01" + expiry.to_bytes(8, "little") + signature + message.encode()
        ).decode()
        response = self.url_open(
            f"{oauth._CALLBACK_PATH}?{urlencode({'state': state, 'code': 'c'})}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(_REFUSED, response.text)

    def _create_oauth_credential(self):
        service = self.env["integration.service"].create(
            {
                "name": "OAuth State Service",
                "code": "oauth_state_test",
                "endpoint_url": "https://api.oauth.test",
                "auth_type": "oauth2",
                "oauth_client_id": "app-client-id",
                "oauth_auth_endpoint": "https://oauth.test/authorize",
                "oauth_token_endpoint": "https://oauth.test/token",
            }
        )
        return self.env["credential.credential"].create(
            {
                "name": "OAuth State Credential",
                "category_id": self.env.ref("credential.credential_category_oauth2").id,
                "endpoint_id": service.id,
                "company_id": self.env.company.id,
            }
        )

    def _get_authorize_response(self, credential):
        return self.url_open(
            f"/api_transport/oauth/authorize/{credential.id}", allow_redirects=False
        )

    def _get_callback_response(self, state):
        return self.url_open(
            f"{oauth._CALLBACK_PATH}?{urlencode({'state': state, 'code': 'c'})}",
            allow_redirects=False,
        )

    def _issue_state(self, credential):
        response = self._get_authorize_response(credential)
        self.assertEqual(response.status_code, 303)
        return parse_qs(urlsplit(response.headers["Location"]).query)["state"][0]

    def _exchange_patched(self):
        return patch.object(
            OAuthController,
            "_exchange_code_for_tokens",
            return_value={"access_token": "issued-token"},
        )

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_the_state_the_authorize_route_issues_passes_the_callback_once(self):
        credential = self._create_oauth_credential()
        self.authenticate("oauth_admin", "oauth_admin")
        state = self._issue_state(credential)
        with self._exchange_patched() as exchange:
            response = self._get_callback_response(state)
            self.assertEqual(response.status_code, 303, response.text)
            self.assertIn(f"id={credential.id}&", response.headers["Location"])
            replayed = self._get_callback_response(state)
        self.assertIn(_REFUSED, replayed.text)
        exchange.assert_called_once()

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_an_expired_state_is_refused(self):
        credential = self._create_oauth_credential()
        self.authenticate("oauth_admin", "oauth_admin")
        state = self._issue_state(credential)
        later = SimpleNamespace(
            time=lambda: time.time() + oauth._OAUTH_STATE_MAX_AGE_SECONDS + 1
        )
        with (
            self._exchange_patched() as exchange,
            patch.object(security, "time", later),
        ):
            response = self._get_callback_response(state)
        self.assertIn(_REFUSED, response.text)
        exchange.assert_not_called()

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_state_issued_in_another_session_is_refused(self):
        credential = self._create_oauth_credential()
        self.authenticate("oauth_admin", "oauth_admin")
        state = self._issue_state(credential)
        self.authenticate("oauth_admin", "oauth_admin")
        self._issue_state(credential)
        with self._exchange_patched() as exchange:
            response = self._get_callback_response(state)
        self.assertIn(_REFUSED, response.text)
        exchange.assert_not_called()

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_signed_state_whose_nonce_is_no_ascii_string_is_refused_as_a_bad_nonce(
        self,
    ):
        credential = self._create_oauth_credential()
        self.authenticate("oauth_admin", "oauth_admin")
        self._issue_state(credential)
        uid = self.env["res.users"].search([("login", "=", "oauth_admin")]).id
        forged = hash_sign(
            self.env,
            oauth.OAUTH_STATE_SCOPE,
            {
                "credential_id": credential.id,
                "db": self.env.cr.dbname,
                "uid": uid,
                "nonce": "é" * 43,
            },
            expiration_hours=1,
        )
        with self._exchange_patched() as exchange:
            response = self._get_callback_response(forged)
        self.assertIn(_REFUSED, response.text)
        exchange.assert_not_called()
