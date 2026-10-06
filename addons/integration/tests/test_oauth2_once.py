import base64
import hashlib
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools import mute_logger

from odoo.addons.integration.tests.common import revealed
from odoo.addons.integration.tools.exceptions import AuthenticationError

_REFUSED = "OAuth Authorization Error"


def _token_response(**body):
    response = MagicMock()
    response.ok = True
    response.json.return_value = {
        "access_token": "issued-access",
        "refresh_token": "issued-refresh",
        "expires_in": 3600,
        **body,
    }
    response.raise_for_status.return_value = None
    return response


def _api_response(status_code, json_data=None):
    response = Mock(headers={"content-type": "application/json"})
    response.status_code = status_code
    response.headers = {}
    response.ok = status_code < 400
    response.content = b"{}"
    response.json.return_value = json_data or {}
    response.text = "{}"
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
    else:
        response.raise_for_status.return_value = None
    return response


class OAuthOnceCase(HttpCase):
    """One OAuth 2.0 flow for every connection a service may have.

    integration authorized only a company credential, as a credential
    administrator, and returned to the credential form; a Google calendar is
    one user's, a Gmail server one record's, and each carried its own copy of
    the authorize URL, the state, the callback and the code exchange.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service = cls.env["integration.service"].create(
            {
                "name": "OAuth Once",
                "code": "oauth_once",
                "endpoint_url": "https://api.once.test",
                "environment": "production",
                "auth_type": "oauth2",
                "allow_user_credentials": True,
                "oauth_client_id": "app-client-id",
                "oauth_auth_endpoint": "https://login.once.test/authorize",
                "oauth_token_endpoint": "https://login.once.test/token",
                "oauth_scope": "read",
                "oauth_authorize_params": '{"access_type": "offline", "prompt": "consent"}',
            }
        )
        cls.category_oauth2 = cls.env.ref("credential.credential_category_oauth2")
        cls.app_credential = cls.env["credential.credential"].create(
            {
                "name": "Once app",
                "category_id": cls.category_oauth2.id,
                "endpoint_id": cls.service.id,
                "company_id": cls.env.company.id,
                "environment": "production",
                "oauth_client_secret": "app-secret",
            }
        )
        cls.alice = new_test_user(
            cls.env,
            login="once_alice",
            groups="base.group_user,base.group_partner_manager",
        )
        cls.bob = new_test_user(cls.env, login="once_bob", groups="base.group_user")
        cls.portal = new_test_user(
            cls.env, login="once_portal", groups="base.group_portal"
        )
        cls.personal = cls.env["integration.connection"].create(
            {
                "service_id": cls.service.id,
                "company_id": cls.env.company.id,
                "user_id": cls.alice.id,
                "environment": "production",
            }
        )
        cls.partner = cls.env["res.partner"].create({"name": "Once mailbox"})
        cls.bound = cls.env["integration.connection"].create(
            {
                "service_id": cls.service.id,
                "company_id": cls.env.company.id,
                "environment": "production",
                "res_model": "res.partner",
                "res_id": cls.partner.id,
            }
        )

    def _authorize(self, connection, **params):
        query = f"?{urlencode(params)}" if params else ""
        return self.url_open(
            f"/integration/oauth/authorize/{connection.id}{query}",
            allow_redirects=False,
        )

    def _authorize_query(self, connection, **params):
        response = self._authorize(connection, **params)
        self.assertEqual(response.status_code, 303, response.text)
        location = urlsplit(response.headers["Location"])
        return location, {
            key: values[0] for key, values in parse_qs(location.query).items()
        }

    @contextmanager
    def _provider(self, **token_body):
        with patch.object(
            requests.Session, "post", return_value=_token_response(**token_body)
        ) as post:
            yield post

    def _callback(self, query, path="/integration/oauth/callback", code="the-code"):
        return self.url_open(
            f"{path}?{urlencode({'state': query['state'], 'code': code})}",
            allow_redirects=False,
        )


@tagged("post_install", "-at_install", "integration")
class TestWhoAuthorizes(OAuthOnceCase):
    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_user_authorizes_their_own_personal_connection(self):
        self.authenticate("once_alice", "once_alice")
        location, query = self._authorize_query(self.personal)
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}",
            "https://login.once.test/authorize",
        )
        self.assertEqual(query["client_id"], "app-client-id")

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_nobody_else_authorizes_a_personal_connection(self):
        self.authenticate("once_bob", "once_bob")
        response = self._authorize(self.personal)
        self.assertNotEqual(response.status_code, 303)
        self.assertIn(_REFUSED, response.text)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_whoever_may_write_the_record_authorizes_its_connection(self):
        self.authenticate("once_alice", "once_alice")
        self._authorize_query(self.bound)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_whoever_may_not_write_the_record_does_not(self):
        self.authenticate("once_portal", "once_portal")
        response = self._authorize(self.bound)
        self.assertNotEqual(response.status_code, 303)


@tagged("post_install", "-at_install", "integration")
class TestAuthorizeRequest(OAuthOnceCase):
    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_the_connection_scope_and_the_service_parameters_are_asked_for(self):
        self.personal.oauth_scope = "calendar"
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(self.personal)
        self.assertEqual(query["scope"], "calendar")
        self.assertEqual(query["access_type"], "offline")
        self.assertEqual(query["prompt"], "consent")

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_the_redirect_is_the_services_path(self):
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(self.personal)
        self.assertTrue(query["redirect_uri"].endswith("/integration/oauth/callback"))
        self.service.oauth_redirect_path = "/api_gateway/oauth/callback"
        _location, query = self._authorize_query(self.personal)
        self.assertTrue(query["redirect_uri"].endswith("/api_gateway/oauth/callback"))

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_pkce_proves_the_code_was_asked_for_here(self):
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(self.personal)
        self.assertEqual(query["code_challenge_method"], "S256")
        with self._provider() as post:
            self._callback(query)
        verifier = post.call_args.kwargs["data"]["code_verifier"]
        digest = hashlib.sha256(verifier.encode()).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge"], challenge)
        self.assertNotIn(verifier, query["state"])

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_service_without_pkce_asks_for_none(self):
        self.service.oauth_use_pkce = False
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(self.personal)
        self.assertNotIn("code_challenge", query)


@tagged("post_install", "-at_install", "integration")
class TestCallback(OAuthOnceCase):
    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_the_tokens_land_in_a_credential_of_the_user_and_the_user_returns(self):
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(
            self.personal, return_url="/odoo/calendar"
        )
        with self._provider() as post:
            response = self._callback(query)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertTrue(response.headers["Location"].endswith("/odoo/calendar"))
        sent = post.call_args.kwargs["data"]
        self.assertEqual(sent["client_secret"], "app-secret")
        self.assertEqual(sent["redirect_uri"], query["redirect_uri"])
        self.personal.invalidate_recordset()
        credential = self.personal.credential_id.sudo()
        self.assertEqual(credential.owner_user_id, self.alice)
        self.assertEqual(credential.oauth_access_token, "issued-access")
        self.assertEqual(credential.oauth_refresh_token, "issued-refresh")
        self.assertTrue(credential.oauth_token_date_expiration)
        self.assertEqual(self.personal.oauth_redirect_uri, query["redirect_uri"])

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_return_url_off_this_site_is_dropped(self):
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(
            self.personal, return_url="https://elsewhere.test/steal"
        )
        with self._provider():
            response = self._callback(query)
        self.assertNotIn("elsewhere.test", response.headers["Location"])

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_the_paths_registered_before_answer_too(self):
        for path in ("/api_gateway/oauth/callback", "/api_transport/oauth/callback"):
            with self.subTest(path=path):
                self.service.oauth_redirect_path = path
                self.authenticate("once_alice", "once_alice")
                _location, query = self._authorize_query(self.personal)
                with self._provider():
                    response = self._callback(query, path=path)
                self.assertEqual(response.status_code, 303, response.text)

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_the_bound_record_hears_of_its_authorization(self):
        heard = []
        partner_class = type(self.env["res.partner"])
        with patch.object(
            partner_class,
            "_on_oauth_authorized",
            lambda record, connection, tokens: heard.append(
                (record.id, connection.id, tokens["access_token"])
            ),
            create=True,
        ):
            self.authenticate("once_alice", "once_alice")
            _location, query = self._authorize_query(self.bound)
            with self._provider():
                self._callback(query)
        self.assertEqual(heard, [(self.partner.id, self.bound.id, "issued-access")])

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def test_a_service_that_wants_the_scope_back_gets_it_with_the_code(self):
        self.service.oauth_token_sends_scope = True
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(self.personal)
        with self._provider() as post:
            self._callback(query)
        self.assertEqual(post.call_args.kwargs["data"]["scope"], "read")


@tagged("post_install", "-at_install", "integration")
class TestTokenUse(OAuthOnceCase):
    def setUp(self):
        super().setUp()
        self.token_credential = (
            self.env["credential.credential"]
            .sudo()
            .create(
                {
                    "name": "Alice's tokens",
                    "category_id": self.category_oauth2.id,
                    "company_id": self.env.company.id,
                    "environment": "production",
                    "owner_user_id": self.alice.id,
                    "oauth_access_token": "old-access",
                    "oauth_refresh_token": "the-refresh",
                    "oauth_token_date_expiration": fields.Datetime.now()
                    + timedelta(hours=1),
                }
            )
        )
        self.personal.credential_id = self.token_credential

    def _refresh_grant(self, response):
        credential_class = type(self.env["credential.credential"])
        return patch.object(
            credential_class, "_post_oauth2_refresh_grant", return_value=response
        )

    def _client(self):
        return self.personal.sudo()._get_api_client()

    @patch("requests.Session.request")
    def test_an_expired_token_is_refreshed_before_the_call(self, request):
        self.token_credential.oauth_token_date_expiration = (
            fields.Datetime.now() - timedelta(minutes=5)
        )
        request.return_value = _api_response(200, {"ok": True})
        with self._refresh_grant(_token_response(access_token="fresh-access")) as grant:
            self._client().get("/events")
        grant.assert_called_once()
        sent = revealed(request.call_args.kwargs["headers"])
        self.assertEqual(sent["Authorization"], "Bearer fresh-access")

    @patch("requests.Session.request")
    def test_a_refused_token_is_refreshed_once_and_the_call_sent_again(self, request):
        request.side_effect = [_api_response(401), _api_response(200, {"ok": True})]
        with self._refresh_grant(_token_response(access_token="fresh-access")) as grant:
            self._client().get("/events")
        grant.assert_called_once()
        self.assertEqual(request.call_count, 2)
        sent = revealed(request.call_args.kwargs["headers"])
        self.assertEqual(sent["Authorization"], "Bearer fresh-access")

    @mute_logger("odoo.addons.integration.tools.api_client")
    @patch("requests.Session.request")
    def test_a_token_refused_after_its_refresh_is_an_authentication_error(
        self, request
    ):
        request.side_effect = [_api_response(401), _api_response(401)]
        with (
            self._refresh_grant(_token_response(access_token="fresh-access")) as grant,
            self.assertRaises(AuthenticationError),
        ):
            self._client().get("/events")
        grant.assert_called_once()
        self.assertEqual(request.call_count, 2)

    @mute_logger(
        "odoo.addons.integration.tools.api_client",
        "odoo.addons.integration.models.integration_connection",
    )
    @patch("requests.Session.request")
    def test_a_revoked_grant_asks_for_a_new_authorization(self, request):
        self.token_credential.oauth_token_date_expiration = (
            fields.Datetime.now() - timedelta(minutes=5)
        )
        refused = _api_response(400, {"error": "invalid_grant"})
        # not assertRaises: its savepoint would take the flag back with it
        with self._refresh_grant(refused):
            try:
                self._client().get("/events")
            except AuthenticationError:
                pass
            else:
                self.fail("a revoked grant must stop the call")
        request.assert_not_called()
        self.assertTrue(self.personal.needs_reauthorization)


@tagged("post_install", "-at_install", "integration")
class TestOneFlowEndToEnd(OAuthOnceCase):
    """authorize -> callback -> call -> forced expiry -> refresh -> 401 -> refresh,
    for a personal connection and for one bound to a record."""

    @mute_logger("odoo.addons.integration.controllers.oauth")
    def _run(self, connection):
        self.authenticate("once_alice", "once_alice")
        _location, query = self._authorize_query(connection)
        with self._provider():
            self.assertEqual(self._callback(query).status_code, 303)
        connection.invalidate_recordset()
        credential = connection.credential_id.sudo()
        self.assertEqual(credential.oauth_access_token, "issued-access")

        def client():
            return connection.sudo()._get_api_client()

        grants = iter(
            [
                _token_response(access_token="second"),
                _token_response(access_token="third"),
            ]
        )
        credential_class = type(self.env["credential.credential"])
        with (
            patch.object(
                credential_class,
                "_post_oauth2_refresh_grant",
                side_effect=lambda *a, **k: next(grants),
            ),
            patch("requests.Session.request") as request,
        ):
            request.return_value = _api_response(200)
            client().get("/a")
            self.assertEqual(
                revealed(request.call_args.kwargs["headers"])["Authorization"],
                "Bearer issued-access",
            )
            credential.oauth_token_date_expiration = fields.Datetime.now() - timedelta(
                minutes=5
            )
            client().get("/b")
            self.assertEqual(
                revealed(request.call_args.kwargs["headers"])["Authorization"],
                "Bearer second",
            )
            request.return_value = None
            request.side_effect = [_api_response(401), _api_response(200)]
            client().get("/c")
            self.assertEqual(
                revealed(request.call_args.kwargs["headers"])["Authorization"],
                "Bearer third",
            )

    def test_a_personal_connection(self):
        self._run(self.personal)

    def test_a_connection_bound_to_a_record(self):
        self._run(self.bound)
