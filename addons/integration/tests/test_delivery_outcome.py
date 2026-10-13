import uuid
from unittest.mock import patch

import requests
from urllib3.exceptions import (
    MaxRetryError,
    NameResolutionError,
    NewConnectionError,
    ProtocolError,
)

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.integration.tools import get_api_client
from odoo.addons.integration.tools.exceptions import (
    CircuitOpenError,
    CommError,
    CommTimeoutError,
    HostNotAllowedError,
    ServerError,
)

URL = "https://example.invalid/api/thing"


def _unreachable(reason):
    return requests.exceptions.ConnectionError(MaxRetryError(None, URL, reason=reason))


@tagged("post_install", "-at_install")
class TestDeliveryOutcome(TransactionCase):
    def _get_client(self):
        endpoint = self.env["integration.service"].create(
            {
                "name": "delivery probe",
                "code": f"delivery_probe_{uuid.uuid4().hex}",
                "endpoint_url": "https://example.invalid/api",
                "auth_type": "none",
                "retry_enabled": False,
            }
        )
        return endpoint, get_api_client(self.env, endpoint.code)

    @mute_logger("odoo.addons.integration.tools.api_client")
    def _post_failing(self, error):
        _endpoint, client = self._get_client()
        with (
            patch.object(client.session, "request", side_effect=error),
            self.assertRaises(CommError) as caught,
        ):
            client.post("/thing", json={})
        self.assertIs(
            caught.exception.__cause__,
            error,
            "each call starts on a fresh endpoint, so no breaker answers for it",
        )
        return caught.exception

    def _http_error(self, status):
        response = requests.Response()
        response.status_code = status
        response._content = b'{"message": "nope"}'
        response.url = URL
        return requests.exceptions.HTTPError(response=response)

    def test_a_request_that_never_reached_the_counterparty_is_undelivered(self):
        for error in (
            requests.exceptions.ConnectTimeout("connect timed out"),
            _unreachable(NewConnectionError(None, "connection refused")),
            _unreachable(NameResolutionError("example.invalid", None, "no name")),
            requests.exceptions.SSLError("handshake failure"),
            requests.exceptions.ProxyError("proxy refused"),
            requests.exceptions.InvalidURL("destination refused"),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertFalse(self._post_failing(error).is_delivered)

    def test_a_request_that_may_have_arrived_is_delivered(self):
        for error in (
            requests.exceptions.ReadTimeout("read timed out"),
            _unreachable(ProtocolError("Connection aborted.", ConnectionResetError())),
            requests.exceptions.ConnectionError("connection dropped"),
            requests.exceptions.ChunkedEncodingError("response ended early"),
            self._http_error(502),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertTrue(self._post_failing(error).is_delivered)

    def test_a_connect_timeout_and_a_read_timeout_are_both_timeouts(self):
        connect = self._post_failing(requests.exceptions.ConnectTimeout("connect"))
        read = self._post_failing(requests.exceptions.ReadTimeout("read"))
        self.assertIsInstance(connect, CommTimeoutError)
        self.assertIsInstance(read, CommTimeoutError)
        self.assertFalse(connect.is_delivered)
        self.assertTrue(read.is_delivered)

    def test_a_5xx_is_delivered(self):
        error = self._post_failing(self._http_error(502))
        self.assertIsInstance(error, ServerError)
        self.assertTrue(error.is_delivered)

    def test_a_malformed_endpoint_url_never_leaves(self):
        _endpoint, client = self._get_client()
        client.base_url = "ftp://example.invalid/api"
        with (
            patch.object(client.session, "request") as request,
            self.assertRaises(CommError) as caught,
        ):
            client.post("/thing", json={})
        request.assert_not_called()
        self.assertFalse(caught.exception.is_delivered)

    def test_a_client_that_cannot_be_built_sends_nothing(self):
        endpoint, _client = self._get_client()
        endpoint.auth_type = "bearer"
        with self.assertRaises(CommError) as caught:
            get_api_client(self.env, endpoint.code)
        self.assertFalse(caught.exception.is_delivered)

    def test_refusals_on_our_side_are_undelivered_by_kind(self):
        self.assertFalse(CircuitOpenError().is_delivered)
        self.assertFalse(HostNotAllowedError().is_delivered)
        self.assertTrue(CommError("unknown").is_delivered)
        self.assertTrue(CommTimeoutError().is_delivered)
