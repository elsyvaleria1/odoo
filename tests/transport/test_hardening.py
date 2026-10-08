import logging
import socket
import time

import pytest

from ._wire import parse_responses, serving, talk


def _environ_echo(environ, start_response):
    if environ["PATH_INFO"] == "/reject":
        start_response("413 Content Too Large", [("Content-Length", "0")])
        return [b""]
    body = environ["wsgi.input"].read()
    out = (environ.get("HTTP_COOKIE", "") + "|" + str(len(body))).encode()
    start_response("200 OK", [("Content-Length", str(len(out)))])
    return [out]


@pytest.fixture
def server():
    with serving(_environ_echo) as srv:
        yield srv


def test_repeated_cookie_fields_join_as_one_cookie_list(server):
    raw = talk(
        server.server_port,
        b"GET / HTTP/1.1\r\nHost: h\r\nCookie: a=1\r\nX-Dup: 1\r\nCookie: b=2; c=3\r\n"
        b"Connection: close\r\n\r\n",
    )
    [reply] = parse_responses(raw)
    assert reply.body == b"a=1; b=2; c=3|0"


def test_the_logged_line_of_a_malformed_request_is_capped(server, caplog):
    target = b"/" + b"a" * 5000
    with caplog.at_level(logging.INFO, logger="odoo.service.http.access"):
        raw = talk(
            server.server_port,
            b"GET " + target + b" HTTP/1.1\r\nHost: h\r\nX-Bad : 1\r\n\r\n",
        )
    assert parse_responses(raw)[0].status == 400
    [record] = [r for r in caplog.records if r.name == "odoo.service.http.access"]
    assert record.args[0] == "GET " + "/" + "a" * 507


def test_a_body_withheld_behind_100_continue_closes_at_once():
    with (
        serving(_environ_echo) as srv,
        socket.create_connection(("127.0.0.1", srv.server_port)) as sock,
    ):
        sock.settimeout(5)
        started = time.monotonic()
        sock.sendall(
            b"PUT /reject HTTP/1.1\r\nHost: h\r\nExpect: 100-continue\r\n"
            b"Content-Length: 3000000\r\n\r\n"
        )
        buf = b""
        while chunk := sock.recv(65536):
            buf += chunk
        elapsed = time.monotonic() - started
    assert b"100 Continue" not in buf
    [reply] = parse_responses(buf)
    assert reply.status == 413
    assert reply.headers["connection"] == "close", (
        "the client is still holding a body back; only a close tells it not to send"
    )
    assert elapsed < 0.5, (
        f"{elapsed:.1f}s: the server drained and lingered for a body that was "
        "never asked for"
    )


def test_a_body_read_behind_100_continue_keeps_the_connection(server):
    with socket.create_connection(("127.0.0.1", server.server_port)) as sock:
        sock.settimeout(5)
        sock.sendall(
            b"PUT /c HTTP/1.1\r\nHost: h\r\nExpect: 100-continue\r\n"
            b"Content-Length: 3\r\n\r\n"
        )
        assert sock.recv(1024).startswith(b"HTTP/1.1 100 Continue")
        sock.sendall(b"abc")
        buf = b""
        while b"|3" not in buf:
            buf += sock.recv(65536)
    [reply] = parse_responses(buf)
    assert reply.status == 200
    assert "connection" not in reply.headers
