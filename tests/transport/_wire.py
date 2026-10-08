import contextlib
import os
import socket
import threading
from dataclasses import dataclass
from unittest.mock import patch

import h11

from odoo.service import httpd
from odoo.service import settings as server_settings

STILL_OPEN = b"<still open>"


@dataclass(frozen=True)
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes


@contextlib.contextmanager
def serving(app, **env):
    with (
        patch.dict(os.environ, {"ODOO_MAX_HTTP_THREADS": "4", **env}),
        server_settings.override(
            db_maxconn=64, max_cron_threads=0, job_workers=0, test_enable=False
        ),
    ):
        srv = httpd.ThreadedHTTPServer("127.0.0.1", 0, app, announce=False)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(5)


def talk(port: int, payload: bytes, timeout: float = 3.0) -> bytes:
    with socket.create_connection(("127.0.0.1", port)) as sock:
        sock.settimeout(timeout)
        sock.sendall(payload)
        buf = b""
        try:
            while chunk := sock.recv(65536):
                buf += chunk
        except TimeoutError:
            buf += STILL_OPEN
    return buf


def parse_responses(raw: bytes, methods: tuple[str, ...] = ()) -> list[Reply]:
    replies = []
    rest = raw.removesuffix(STILL_OPEN)
    while rest:
        method = methods[len(replies)] if len(replies) < len(methods) else "GET"
        conn = h11.Connection(h11.CLIENT)
        conn.send(h11.Request(method=method, target="/", headers=[("Host", "h")]))
        conn.send(h11.EndOfMessage())
        conn.receive_data(rest)
        conn.receive_data(b"")
        status, headers, body = 0, {}, b""
        while not isinstance(event := conn.next_event(), h11.EndOfMessage):
            if isinstance(event, h11.Response):
                status = event.status_code
                headers = {k.decode().lower(): v.decode() for k, v in event.headers}
            elif isinstance(event, h11.Data):
                body += event.data
            elif not isinstance(event, h11.InformationalResponse):
                raise AssertionError(f"response {len(replies) + 1} cut short: {event}")
        replies.append(Reply(status, headers, body))
        rest = conn.trailing_data[0]
    return replies
