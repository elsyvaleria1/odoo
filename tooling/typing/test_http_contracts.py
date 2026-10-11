import unittest
import xmlrpc.client
from array import array
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import override
from unittest.mock import patch

from requests import Response, Session
from urllib3 import HTTPConnectionPool, HTTPSConnectionPool

from odoo.libs.guarded_http import (
    GuardedXmlRpcTransport,
    _WatchedHTTPConnectionPool,
    _WatchedHTTPSConnectionPool,
)


class HttpContractTests(unittest.TestCase):
    def test_xmlrpc_buffer_bodies_have_correct_wire_length(self) -> None:
        received: list[bytes] = []
        response = xmlrpc.client.dumps((42,), methodresponse=True).encode()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                received.append(self.rfile.read(int(self.headers["Content-Length"])))
                self.send_response(200)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            @override
            def log_message(self, format: str, *args: object) -> None:
                pass

        body = xmlrpc.client.dumps((1,), methodname="sample").encode()
        body += b" " * (-len(body) % 4)
        words = array("I")
        words.frombytes(body)

        class BufferOnly:
            def __buffer__(self, flags: int) -> memoryview:
                return memoryview(body)

        with HTTPServer(("127.0.0.1", 0), Handler) as server:
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                with Session() as session:
                    session.trust_env = False
                    url = f"http://127.0.0.1:{server.server_port}"
                    transport = GuardedXmlRpcTransport(session, url, timeout=5)
                    for value in (
                        body,
                        memoryview(bytearray(body)),
                        memoryview(words),
                        BufferOnly(),
                    ):
                        with self.subTest(buffer=type(value).__name__):
                            self.assertEqual(
                                transport.request("127.0.0.1", "/RPC2", value), (42,)
                            )
                            self.assertEqual(received[-1], body)
            finally:
                server.shutdown()
                worker.join(timeout=5)
                self.assertFalse(worker.is_alive())

    def test_xmlrpc_accepts_transport_hosts_and_writable_buffers(self) -> None:
        response = Response()
        response.status_code = 200
        response._content = xmlrpc.client.dumps((42,), methodresponse=True).encode()
        body = memoryview(
            bytearray(xmlrpc.client.dumps((1,), methodname="sample").encode())
        )
        with (
            Session() as session,
            patch.object(session, "post", return_value=response) as post,
        ):
            transport = GuardedXmlRpcTransport(session, "https://example.test/")
            result = transport.request(
                ("user:password@example.test", {}), "/RPC2", body
            )
        self.assertEqual(result, (42,))
        self.assertEqual(post.call_args.kwargs["data"], body.tobytes())
        self.assertEqual(post.call_args.args, ("https://example.test/RPC2",))
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Basic dXNlcjpwYXNzd29yZA==",
        )

    def test_pool_super_calls_reach_the_http_and_https_implementations(self) -> None:
        for pool_class in (_WatchedHTTPConnectionPool, _WatchedHTTPSConnectionPool):
            with self.subTest(pool=pool_class.__name__):
                pool = pool_class("example.test")
                with (
                    patch.object(
                        HTTPConnectionPool, "urlopen", return_value="http response"
                    ) as urlopen,
                    patch.object(
                        HTTPConnectionPool,
                        "_make_request",
                        return_value="request result",
                    ) as http_request,
                    patch.object(
                        HTTPSConnectionPool,
                        "_make_request",
                        return_value="TLS request result",
                    ) as https_request,
                ):
                    self.assertEqual(pool.urlopen("GET", "/"), "http response")
                    result = pool._make_request(object(), "GET", "/")
                    if isinstance(pool, HTTPSConnectionPool):
                        self.assertEqual(result, "TLS request result")
                        https_request.assert_called_once()
                        http_request.assert_not_called()
                    else:
                        self.assertEqual(result, "request result")
                        http_request.assert_called_once()
                        https_request.assert_not_called()
                    urlopen.assert_called_once()
                pool.close()
