import os
import socket
import ssl
import threading
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
from odoo.tools import file_path, mute_logger

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


class _TlsCounterparty:
    def __init__(self, answer):
        self.answer = answer
        self.received = []
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(
            file_path("base/tests/ssl/self_signed.cert.pem"),
            file_path("base/tests/ssl/self_signed.key.pem"),
        )
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listener.settimeout(10)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def close(self):
        self.listener.shutdown(socket.SHUT_RDWR)
        self.listener.close()
        self.thread.join(10)

    def _serve(self):
        while True:
            try:
                raw, _address = self.listener.accept()
            except OSError:
                return
            with raw:
                try:
                    connection = self.context.wrap_socket(raw, server_side=True)
                    self.received.append(self._read_request(connection))
                    self.answer(connection)
                except OSError, ValueError:
                    continue

    def _read_request(self, connection):
        data = b""
        while b"\r\n\r\n" not in data:
            data += connection.recv(65536)
        head, _separator, body = data.partition(b"\r\n\r\n")
        length = next(
            int(line.partition(b":")[2])
            for line in head.split(b"\r\n")
            if line.lower().startswith(b"content-length:")
        )
        while len(body) < length:
            body += connection.recv(65536)
        return body


def _garble_the_answer(connection):
    os.write(connection.fileno(), b"\x17\x03\x03\x00\x20" + os.urandom(32))


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
            requests.exceptions.SSLError("record failure"),
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

    def _post_to(self, counterparty, verify_tls, retry_enabled):
        endpoint = self.env["integration.service"].create(
            {
                "name": "tls probe",
                "code": f"tls_probe_{uuid.uuid4().hex}",
                "endpoint_url": f"https://127.0.0.1:{counterparty.port}/api",
                "auth_type": "none",
                "verify_tls": verify_tls,
                "retry_enabled": retry_enabled,
                "retry_max_attempts": 3,
                "timeout_connect": 5,
                "timeout_read": 5,
            }
        )
        client = get_api_client(self.env, endpoint.code)
        with (
            mute_logger("odoo.addons.integration.tools.api_client", "py.warnings"),
            self.assertRaises(CommError) as caught,
        ):
            client.post("/thing", json={"document": 1})
        return caught.exception

    def test_a_tls_failure_after_the_request_arrived_is_delivered_and_not_resent(
        self,
    ):
        counterparty = _TlsCounterparty(_garble_the_answer)
        self.addCleanup(counterparty.close)

        error = self._post_to(counterparty, verify_tls=False, retry_enabled=True)

        self.assertEqual(
            len(counterparty.received),
            1,
            "the transport retried a POST the counterparty had already read",
        )
        self.assertTrue(
            error.is_delivered,
            "the counterparty read the request before the TLS stream broke",
        )

    def test_a_tls_handshake_failure_never_reaches_the_counterparty(self):
        counterparty = _TlsCounterparty(_garble_the_answer)
        self.addCleanup(counterparty.close)

        error = self._post_to(counterparty, verify_tls=True, retry_enabled=False)

        self.assertEqual(counterparty.received, [])
        self.assertFalse(error.is_delivered)

    def test_a_credential_that_cannot_be_fetched_sends_nothing(self):
        _endpoint, client = self._get_client()
        with (
            patch.object(
                type(client),
                "_acquire_headers",
                side_effect=requests.exceptions.ConnectionError("token endpoint down"),
            ),
            patch.object(client.session, "request") as request,
            mute_logger("odoo.addons.integration.tools.api_client"),
            self.assertRaises(CommError) as caught,
        ):
            client.post("/thing", json={})
        request.assert_not_called()
        self.assertFalse(caught.exception.is_delivered)
