import contextlib
import socket
import threading
import time

import pytest

from ._wire import STILL_OPEN, parse_responses, serving, talk

SMUGGLED = b"GET /smuggled HTTP/1.1\r\nHost: h\r\n\r\n"


class Recorder:
    def __init__(self):
        self.paths = []
        self.lock = threading.Lock()

    def __call__(self, environ, start_response):
        with self.lock:
            self.paths.append(environ["PATH_INFO"])
        if environ["PATH_INFO"] == "/reject":
            start_response("413 Content Too Large", [("Content-Length", "0")])
            return [b""]
        body = environ["wsgi.input"].read()
        out = b"%d" % len(body)
        start_response("200 OK", [("Content-Length", str(len(out)))])
        return [out]


@pytest.fixture
def recorder():
    return Recorder()


@pytest.fixture
def server(recorder):
    with serving(recorder) as srv:
        yield srv


def _post(framing: bytes, body: bytes = b"", version: bytes = b"HTTP/1.1") -> bytes:
    return b"POST /c " + version + b"\r\nHost: h\r\n" + framing + b"\r\n" + body


@pytest.mark.parametrize(
    ("framing", "status"),
    [
        (b"Content-Length: 5, 6\r\n", 400),
        (b"Content-Length: 5\r\nContent-Length: 6\r\n", 400),
        (b"Content-Length: +5\r\n", 400),
        (b"Content-Length: -5\r\n", 400),
        (b"Content-Length: 0x5\r\n", 400),
        (b"Content-Length: 5 5\r\n", 400),
        (b"Content-Length: 12345678901234567890\r\n", 400),
        (b"Content-Length:\r\n", 400),
        (b"Transfer-Encoding: gzip, chunked\r\n", 501),
        (b"Transfer-Encoding: chunked, gzip\r\n", 400),
        (b"Transfer-Encoding: chunked, chunked\r\n", 400),
        (b"Transfer-Encoding: chunked\r\nTransfer-Encoding: chunked\r\n", 400),
        (b"Transfer-Encoding: identity\r\n", 400),
        (b"Transfer-Encoding: \xa0chunked\r\n", 400),
        (b"Transfer-Encoding: chunked\xa0\r\n", 400),
        (b"Transfer-Encoding: \x0bchunked\r\n", 400),
        (b"Transfer-Encoding : chunked\r\n", 400),
        (b"Transfer-Encoding:\r\n", 400),
    ],
)
def test_ambiguous_framing_is_refused_and_nothing_behind_it_is_served(
    server, recorder, framing, status
):
    body = b"5\r\nhello\r\n0\r\n\r\n" + SMUGGLED
    [reply] = parse_responses(talk(server.server_port, _post(framing, body)))
    assert reply.status == status
    assert reply.headers["connection"] == "close"
    assert recorder.paths == []


def test_transfer_encoding_on_http10_is_refused(server, recorder):
    raw = talk(
        server.server_port,
        _post(b"Transfer-Encoding: chunked\r\n", b"0\r\n\r\n", b"HTTP/1.0"),
    )
    assert parse_responses(raw)[0].status == 400
    assert recorder.paths == []


def test_content_length_beside_chunked_reads_chunked_and_closes(server, recorder):
    framing = b"Content-Length: 40\r\nTransfer-Encoding: chunked\r\n"
    raw = talk(
        server.server_port, _post(framing, b"5\r\nhello\r\n0\r\n\r\n" + SMUGGLED)
    )
    assert not raw.endswith(STILL_OPEN)
    [reply] = parse_responses(raw)
    assert (reply.status, reply.body) == (200, b"5")
    assert reply.headers["connection"] == "close"
    assert recorder.paths == ["/c"], "the bytes after the chunked body were served"


def test_a_body_shorter_than_content_length_never_lends_its_tail(server, recorder):
    raw = talk(
        server.server_port,
        _post(b"Content-Length: %d\r\n" % len(SMUGGLED), SMUGGLED)
        + SMUGGLED.replace(b"\r\n\r\n", b"\r\nConnection: close\r\n\r\n"),
    )
    replies = parse_responses(raw)
    assert [r.status for r in replies] == [200, 200]
    assert recorder.paths == ["/c", "/smuggled"], (
        "exactly one request follows a body of its declared length"
    )


@pytest.mark.parametrize(
    "wire",
    [
        b"5;name=value\r\nhello\r\n0\r\n\r\n",
        b'5;a;b="q;r"\r\nhello\r\n0;last\r\n\r\n',
        b"5 \t;ext\r\nhello\r\n0\r\n\r\n",
        b"000005\r\nhello\r\n0\r\n\r\n",
        b"5\r\nhello\r\n0\r\nX-Trailer: t\r\nY: u\r\n\r\n",
    ],
)
def test_chunk_extensions_and_trailers_are_skipped(server, recorder, wire):
    framing = b"Transfer-Encoding: chunked\r\nConnection: close\r\n"
    [reply] = parse_responses(talk(server.server_port, _post(framing, wire)))
    assert (reply.status, reply.body) == (200, b"5")


@pytest.mark.parametrize(
    "line",
    [
        b"GET / HTTP/1.1\r\nHost: h\rX: y\r\n\r\n",
        b"GET / HTTP/1.1\rHost: h\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: h\r\nX-Fold: a\r\n b\r\n\r\n",
        b"GET / HTTP/1.1\r\nHost: h\r\nX-Fold: a\r\n\tb\r\n\r\n",
        b"GET / HTTP/1.1\r\n Host: h\r\n\r\n",
    ],
)
def test_a_bare_cr_or_a_folded_line_is_refused(server, recorder, line):
    [reply] = parse_responses(talk(server.server_port, line))
    assert reply.status == 400
    assert recorder.paths == []


def _with_fields(total: int) -> bytes:
    fields = b"".join(b"X-F%d: v\r\n" % i for i in range(total - 2))
    return b"GET / HTTP/1.1\r\nHost: h\r\n" + fields + b"Connection: close\r\n\r\n"


@pytest.mark.parametrize(("total", "status"), [(100, 200), (101, 431)])
def test_a_hundred_fields_pass_and_one_more_is_refused(server, total, status):
    [reply] = parse_responses(talk(server.server_port, _with_fields(total)))
    assert reply.status == status


def _head_of(size: int) -> bytes:
    prefix = b"GET / HTTP/1.1\r\nHost: h\r\nConnection: close\r\nX-Pad: "
    return prefix + b"a" * (size - len(prefix)) + b"\r\n\r\n"


@pytest.mark.parametrize(
    ("size", "status"), [(65535, 200), (65536, 200), (65537, 431), (65538, 431)]
)
def test_the_head_limit_is_64_kib_to_the_byte(server, size, status):
    request = _head_of(size)
    assert len(request) == size + 4
    [reply] = parse_responses(talk(server.server_port, request, timeout=5))
    assert reply.status == status


def test_a_pipeline_past_the_inline_cap_is_answered_without_waiting():
    from odoo.service import httpd

    recorder = Recorder()
    count = httpd._MAX_PIPELINED + 1
    payload = b"".join(
        b"GET /r%d HTTP/1.1\r\nHost: h\r\n\r\n" % i for i in range(count)
    )
    with (
        serving(recorder, ODOO_HTTP_HEAD_TIMEOUT="5") as srv,
        socket.create_connection(("127.0.0.1", srv.server_port)) as sock,
    ):
        sock.settimeout(5)
        started = time.monotonic()
        sock.sendall(payload)
        buf = b""
        while buf.count(b"HTTP/1.1 200 OK") < count:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
        elapsed = time.monotonic() - started
    assert len(parse_responses(buf)) == count
    assert recorder.paths == [f"/r{i}" for i in range(count)]
    assert elapsed < 1.0, (
        f"the {count}th request waited {elapsed:.1f}s: parked until a byte or "
        "the head timeout instead of resubmitted"
    )


def test_a_slowloris_head_gets_a_408_and_never_holds_a_worker():
    recorder = Recorder()
    head = b"GET /slow HTTP/1.1\r\nHost: h\r\nX-Drip: " + b"a" * 64
    busy = []
    with (
        serving(recorder, ODOO_HTTP_HEAD_TIMEOUT="1") as srv,
        socket.create_connection(("127.0.0.1", srv.server_port)) as sock,
    ):
        sock.settimeout(0.4)
        started = time.monotonic()
        buf = b""
        for byte in head:
            busy.append(srv.busy_workers)
            try:
                sock.send(bytes([byte]))
            except OSError:
                break
            with contextlib.suppress(TimeoutError):
                if chunk := sock.recv(4096):
                    buf += chunk
                else:
                    break
            if buf:
                break
        elapsed = time.monotonic() - started
        busy.append(srv.busy_workers)
    assert buf.startswith(b"HTTP/1.1 408")
    assert elapsed < 2.5, f"a 1 s head budget took {elapsed:.1f}s to enforce"
    assert set(busy) == {0}
    assert recorder.paths == []


def test_a_large_refused_upload_still_reads_its_answer_whole(recorder):
    body = b"x" * (4 << 20)
    head = b"POST /reject HTTP/1.1\r\nHost: h\r\nContent-Length: %d\r\n\r\n" % len(body)
    with (
        serving(recorder) as srv,
        socket.create_connection(("127.0.0.1", srv.server_port)) as sock,
    ):
        sock.settimeout(10)
        failure = []

        def upload():
            try:
                sock.sendall(head + body)
            except OSError as exc:
                failure.append(exc)

        sender = threading.Thread(target=upload)
        sender.start()
        buf = b""
        while chunk := sock.recv(65536):
            buf += chunk
        sender.join(10)
    [reply] = parse_responses(buf)
    assert reply.status == 413
    assert reply.headers["content-length"] == "0"
    assert not failure, failure
