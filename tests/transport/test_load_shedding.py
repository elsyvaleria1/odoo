import os
import socket
import threading
import time
from unittest.mock import patch

import pytest

from odoo.service import httpd

from ._wire import parse_responses, serving, talk

GATE = threading.Event()


def _gated(environ, start_response):
    if environ["PATH_INFO"] == "/hold":
        GATE.wait(10)
    start_response("200 OK", [("Content-Length", "2")])
    return [b"ok"]


@pytest.mark.parametrize(
    ("threads", "env", "expected"),
    [(1, None, 64), (4, None, 64), (20, None, 160), (20, "5", 5), (20, "0", 0)],
)
def test_the_queue_bound_follows_the_thread_limit(monkeypatch, threads, env, expected):
    if env is None:
        monkeypatch.delenv("ODOO_HTTP_MAX_QUEUE", raising=False)
    else:
        monkeypatch.setenv("ODOO_HTTP_MAX_QUEUE", env)
    assert httpd.compute_max_queue(threads) == expected


def _read_all(sock):
    buf = b""
    while chunk := sock.recv(65536):
        buf += chunk
    return buf


def test_a_request_past_the_queue_bound_is_shed_at_once_with_retry_after():
    GATE.clear()
    request = b"GET /%s HTTP/1.1\r\nHost: h\r\nConnection: close\r\n\r\n"
    with serving(_gated, ODOO_MAX_HTTP_THREADS="1", ODOO_HTTP_MAX_QUEUE="2") as srv:
        socks = [
            socket.create_connection(("127.0.0.1", srv.server_port)) for _ in range(4)
        ]
        try:
            for sock in socks:
                sock.settimeout(10)
            deadline = time.monotonic() + 5
            while len(srv._idle) < 4 and time.monotonic() < deadline:
                time.sleep(0.01)
            socks[0].sendall(request % b"hold")
            while not srv.busy_workers and time.monotonic() < deadline:
                time.sleep(0.01)
            socks[1].sendall(request % b"a")
            socks[2].sendall(request % b"b")
            while srv._pool.queued < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            started = time.monotonic()
            socks[3].sendall(request % b"c")
            shed = _read_all(socks[3])
            elapsed = time.monotonic() - started
            GATE.set()
            served = [_read_all(sock) for sock in socks[:3]]
        finally:
            GATE.set()
            for sock in socks:
                sock.close()
    [reply] = parse_responses(shed)
    assert reply.status == 503
    assert reply.headers["retry-after"] == "1"
    assert elapsed < 1.0, f"the shed request waited {elapsed:.1f}s"
    assert [parse_responses(raw)[0].status for raw in served] == [200, 200, 200]


def test_the_503_is_written_without_blocking_the_selector():
    seen = []
    real_send = socket.socket.send

    def send(self, data, *args):
        if data.startswith(b"HTTP/1.1 503"):
            seen.append(self.gettimeout())
        return real_send(self, data, *args)

    with (
        serving(_gated) as srv,
        patch.object(srv._pool, "submit", return_value=False),
        patch.object(socket.socket, "send", send),
    ):
        raw = talk(srv.server_port, b"GET / HTTP/1.1\r\nHost: h\r\n\r\n")
    [reply] = parse_responses(raw)
    assert (reply.status, reply.headers["retry-after"]) == (503, "1")
    assert seen == [0.0], "a timeout other than 0 is a send that can block"


def test_an_unbounded_queue_never_sheds():
    with (
        patch.dict(os.environ, {"ODOO_HTTP_MAX_QUEUE": "0"}),
        serving(_gated) as srv,
    ):
        assert srv.max_queue == 0
        raw = talk(
            srv.server_port, b"GET / HTTP/1.1\r\nHost: h\r\nConnection: close\r\n\r\n"
        )
    assert parse_responses(raw)[0].status == 200
