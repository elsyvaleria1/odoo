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


def _drip(port, head, pieces, pause):
    with socket.create_connection(("127.0.0.1", port)) as sock:
        sock.settimeout(10)
        started = time.monotonic()
        sock.sendall(head)
        buf = b""
        for piece in pieces:
            time.sleep(pause)
            try:
                sock.sendall(piece)
            except OSError:
                break
            sock.setblocking(False)
            try:
                buf += sock.recv(65536)
            except BlockingIOError:
                pass
            finally:
                sock.settimeout(10)
            if buf:
                break
        try:
            while chunk := sock.recv(65536):
                buf += chunk
        except ConnectionResetError:
            pass
        return buf, time.monotonic() - started


def test_a_body_dripping_one_byte_per_1_5_s_gets_a_408():
    head = b"POST /c HTTP/1.1\r\nHost: h\r\nContent-Length: 20\r\nConnection: close\r\n\r\n"
    with serving(_environ_echo, ODOO_HTTP_BODY_TIMEOUT="2") as srv:
        buf, elapsed = _drip(srv.server_port, head, [b"x"] * 20, 1.5)
    [reply] = parse_responses(buf)
    assert reply.status == 408
    assert reply.headers["connection"] == "close"
    assert 2.5 < elapsed < 8, f"{elapsed:.1f}s for a 2 s budget"


def test_four_mib_at_one_mib_per_second_passes_a_2_s_budget():
    size = 4 << 20
    head = (
        b"POST /c HTTP/1.1\r\nHost: h\r\nConnection: close\r\nContent-Length: %d\r\n\r\n"
        % size
    )
    piece = b"x" * (1 << 18)
    with serving(_environ_echo, ODOO_HTTP_BODY_TIMEOUT="2") as srv:
        buf, elapsed = _drip(srv.server_port, head, [piece] * 16, 0.25)
    [reply] = parse_responses(buf)
    assert (reply.status, reply.body) == (200, b"|%d" % size)
    assert elapsed > 3.5


def test_a_body_that_stops_arriving_gets_a_408_not_a_silent_close():
    with (
        serving(_environ_echo, ODOO_HTTP_SOCKET_TIMEOUT="0.3") as srv,
        socket.create_connection(("127.0.0.1", srv.server_port)) as sock,
    ):
        sock.settimeout(5)
        sock.sendall(b"POST /c HTTP/1.1\r\nHost: h\r\nContent-Length: 10\r\n\r\nabc")
        buf = b""
        while chunk := sock.recv(65536):
            buf += chunk
    assert parse_responses(buf)[0].status == 408
