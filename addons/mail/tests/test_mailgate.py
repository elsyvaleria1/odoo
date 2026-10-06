import base64
import http.server
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.libs.json import loads as json_loads
from odoo.tests import BaseCase, tagged
from odoo.tools import file_path

EX_NOUSER = 67
EX_UNAVAILABLE = 69
EX_TEMPFAIL = 75


class FakeOdoo:
    def __init__(self, status=200, problem=None):
        outer = self
        self.status = status
        self.problem = problem
        self.received = None
        self.headers = None

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                outer.received = json_loads(self.rfile.read(length))
                outer.headers = dict(self.headers)
                body = json_dumps_bytes(outer.problem or {"delivered": True})
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self._server = http.server.HTTPServer(("127.0.0.1", 0), Handler)

    @property
    def url(self):
        return f"http://127.0.0.1:{self._server.server_address[1]}/mail/inbound/1"

    def __enter__(self):
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc_info):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=10)


@tagged("post_install", "-at_install")
class TestMailgate(BaseCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.script = file_path("mail/static/scripts/odoo-mailgate.py")
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.token_file = Path(directory.name) / "mailgate.token"
        cls.token_file.write_text("s3cret\n", encoding="utf-8")

    def _run(self, message, url, extra=(), token_file=None):
        command = [
            sys.executable,
            self.script,
            f"--url={url}",
            f"--token-file={token_file or self.token_file}",
            "--sender=bounce@example.org",
            "--recipient=orders@example.com",
            *extra,
        ]
        return subprocess.run(
            command, input=message, capture_output=True, timeout=60, check=False
        )

    def _message(self, charset, body):
        return (
            b"From: sender@example.com\r\n"
            b"To: orders@example.com\r\n"
            b"Subject: probe\r\n"
            b"Message-Id: <mailgate@example.com>\r\n"
            b"Content-Type: text/plain; charset=" + charset + b"\r\n"
            b"\r\n" + body + b"\r\n"
        )

    def test_the_message_reaches_odoo_byte_for_byte(self):
        for label, raw in [
            ("ascii", self._message(b"us-ascii", b"plain body")),
            ("utf-8", self._message(b"utf-8", "señor café".encode())),
            (
                "iso-8859-1",
                self._message(b"iso-8859-1", "señor café".encode("latin-1")),
            ),
            ("binary", self._message(b"application/octet-stream", bytes(range(256)))),
            ("crlf", self._message(b"us-ascii", b"one\r\ntwo\r\nthree")),
        ]:
            with self.subTest(charset=label), FakeOdoo() as odoo:
                result = self._run(raw, odoo.url)
                self.assertEqual(
                    result.returncode, 0, result.stderr.decode(errors="replace")
                )
                self.assertEqual(
                    base64.b64decode(odoo.received["message"]),
                    raw,
                    "the bytes must not be touched",
                )

    def test_the_envelope_travels_with_the_message(self):
        with FakeOdoo() as odoo:
            self._run(
                self._message(b"us-ascii", b"x"),
                odoo.url,
                ["--recipient=bcc@example.com"],
            )
        self.assertEqual(odoo.received["sender"], "bounce@example.org")
        self.assertEqual(
            odoo.received["recipients"], ["orders@example.com", "bcc@example.com"]
        )

    def test_the_token_is_a_bearer_read_from_its_file(self):
        with FakeOdoo() as odoo:
            self._run(self._message(b"us-ascii", b"x"), odoo.url)
        self.assertEqual(
            odoo.headers["Authorization"],
            "Bearer s3cret",
            "the newline is not the secret",
        )

    def test_a_duplicate_is_a_delivery(self):
        problem = {"error": "duplicate_event", "detail": "Duplicate event detected"}
        with FakeOdoo(409, problem) as odoo:
            result = self._run(self._message(b"us-ascii", b"x"), odoo.url)
        self.assertEqual(result.returncode, 0, "Odoo already holds it")

    def test_an_unroutable_message_is_an_unknown_user(self):
        problem = {"error": "no_route", "detail": "No possible route found"}
        with FakeOdoo(422, problem) as odoo:
            result = self._run(self._message(b"us-ascii", b"x"), odoo.url)
        self.assertEqual(result.returncode, EX_NOUSER)

    def test_an_oversized_message_is_bounced(self):
        with FakeOdoo(413, {"error": "payload_too_large"}) as odoo:
            result = self._run(self._message(b"us-ascii", b"x"), odoo.url)
        self.assertEqual(result.returncode, EX_UNAVAILABLE)

    def test_every_other_answer_keeps_the_message_queued(self):
        for status, problem in [
            (401, {"error": "auth_failed"}),
            (404, {"error": "endpoint_not_found"}),
            (429, {"error": "rate_limited"}),
            (500, None),
            (502, None),
            (503, None),
            (400, {"error": "invalid_envelope"}),
        ]:
            with self.subTest(status=status), FakeOdoo(status, problem) as odoo:
                result = self._run(self._message(b"us-ascii", b"x"), odoo.url)
                self.assertEqual(
                    result.returncode,
                    EX_TEMPFAIL,
                    "a wrong token, URL or a restart is fixed by someone; "
                    "a bounced customer mail is not",
                )

    def test_an_unreachable_server_defers(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        result = self._run(
            self._message(b"us-ascii", b"x"), f"http://127.0.0.1:{port}/mail/inbound/1"
        )
        self.assertEqual(result.returncode, EX_TEMPFAIL)

    def test_an_unreadable_token_defers_rather_than_bounces(self):
        with FakeOdoo() as odoo:
            result = self._run(
                self._message(b"us-ascii", b"x"),
                odoo.url,
                token_file="/nonexistent/mailgate.token",
            )
        self.assertEqual(
            result.returncode,
            EX_TEMPFAIL,
            "Postfix bounces on EX_CONFIG (5.3.5): a mistyped token path would "
            "return every message to its sender",
        )
        self.assertIsNone(odoo.received, "nothing is sent without a token")

    def test_a_malformed_command_line_defers_rather_than_bounces(self):
        for command in (
            [sys.executable, self.script],
            [sys.executable, self.script, "--url=http://x", "unexpected-argument"],
        ):
            with self.subTest(command=command[2:]):
                result = subprocess.run(
                    command, input=b"x", capture_output=True, timeout=60, check=False
                )
                self.assertEqual(
                    result.returncode,
                    EX_TEMPFAIL,
                    "a master.cf mistake is fixed by its operator; EX_USAGE "
                    "(5.3.0) would bounce the mail meanwhile",
                )
