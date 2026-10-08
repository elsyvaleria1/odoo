import collections
import logging
import os
import random
import re
import socket
import time
from collections import deque

import h11
import pytest

from odoo.libs.http1 import (
    BodyError,
    BodyLimits,
    BufferedSource,
    ChunkedReader,
    HeadLimits,
    LengthReader,
    ProtocolError,
    find_head,
    parse_request_head,
)

from ._wire import STILL_OPEN, serving

SEED = int(os.environ.get("ODOO_TRANSPORT_FUZZ_SEED", "20261007"))
CASES = int(os.environ.get("ODOO_TRANSPORT_FUZZ_CASES", "20000"))
LIVE_CASES = 500
HEAD = HeadLimits()
BODY = BodyLimits()

CORPUS = (
    b"GET / HTTP/1.1\r\nHost: h\r\n\r\n",
    (
        b"GET /a/b?x=1&y=%20 HTTP/1.1\r\nHost: example.com:8069\r\nAccept: */*\r\n"
        b"X-Two: a\r\nX-Two: b\r\n\r\n"
    ),
    (
        b"POST /web/dataset/call_kw HTTP/1.1\r\nHost: h\r\n"
        b"Content-Type: application/json\r\nContent-Length: 10\r\n\r\n"
        b'{"a": [1]}'
    ),
    (
        b"POST /upload HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n"
        b"5\r\nhello\r\n6\r\n world\r\n0\r\nX-Trailer: t\r\n\r\n"
    ),
    b"PUT /c HTTP/1.1\r\nHost: h\r\nExpect: 100-continue\r\nContent-Length: 3\r\n\r\nabc",
    b"GET http://other.example/p?q HTTP/1.1\r\nHost: h\r\n\r\n",
    b"OPTIONS * HTTP/1.1\r\nHost: h\r\n\r\n",
    b"DELETE /x HTTP/1.1\r\nHost: h\r\nContent-Length: 0\r\n\r\n",
    b"GET / HTTP/1.0\r\n\r\n",
    b"POST /c HTTP/1.1\r\nHost: h\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok",
)
SPECIAL = b'\r\n \t:,;\x00\x0b\x7f\xa0\x85\xff0f-+"=/?#%'
FRAMING = (
    b"Content-Length: 5",
    b"Content-Length: 0",
    b"Content-Length: 5, 5",
    b"Content-Length: 10",
    b"Transfer-Encoding: chunked",
    b"Transfer-Encoding: gzip, chunked",
    b"Connection: close",
    b"Expect: 100-continue",
    b"Host: h",
)
CHUNK_LINE = re.compile(rb"(?<=\n)([0-9A-Fa-f]+)((?:;[^\r\n]*)?)(?=\r?\n)")


def pipeline(rng: random.Random) -> bytes:
    return b"".join(rng.choice(CORPUS) for _ in range(rng.randint(1, 3)))


def _lines(data: bytearray) -> list[bytes]:
    return bytes(data).split(b"\r\n")


def mutate(rng: random.Random, original: bytes) -> bytes:
    data = bytearray(original)
    for _ in range(rng.randint(1, 4)):
        if not data:
            break
        op = rng.randrange(11)
        pos = rng.randrange(len(data))
        if op == 0:
            data[pos] = (
                rng.choice(SPECIAL) if rng.random() < 0.7 else rng.randrange(256)
            )
        elif op in (1, 2) and (
            crlf := [m.start() for m in re.finditer(rb"\r\n", data)]
        ):
            at = rng.choice(crlf)
            data[at : at + 2] = b"\n" if op == 1 else b"\r"
        elif op in (3, 4, 5, 6):
            lines = _lines(data)
            if len(lines) < 3:
                continue
            i, j = rng.randrange(1, len(lines)), rng.randrange(1, len(lines))
            if op == 3:
                lines.insert(j, lines[i])
            elif op == 4:
                del lines[i]
            elif op == 5:
                lines[i], lines[j] = lines[j], lines[i]
            else:
                lines.insert(i, rng.choice(FRAMING))
            data = bytearray(b"\r\n".join(lines))
        elif op == 7:
            colon = [m.start() for m in re.finditer(rb":", data)]
            at = rng.choice(colon) + rng.choice((0, 1)) if colon else pos
            data[at:at] = rng.choice((b" ", b"\t", b"  ", b" \t", b"\xa0"))
        elif op == 8 and (sizes := list(CHUNK_LINE.finditer(data))):
            match = rng.choice(sizes)
            size = int(match.group(1), 16)
            replacement = rng.choice(
                (
                    b"%x" % (size + rng.choice((-1, 1, 16))),
                    b"0" * rng.randint(1, 18) + match.group(1),
                    b"f" * 17,
                    match.group(1) + b" ",
                    match.group(1) + b";ext=1",
                    match.group(1) + b';q="a;b"',
                    match.group(1) + b";" + b"e" * 4100,
                    match.group(1).upper(),
                    b"+" + match.group(1),
                    b"",
                )
            )
            data[match.start() : match.end()] = replacement
        elif op == 9:
            del data[pos:]
        else:
            data[pos:pos] = bytes(rng.choice(SPECIAL) for _ in range(rng.randint(1, 8)))
    return bytes(data)


def _find(buffer: bytearray, scanned: int):
    def outcome(*args):
        try:
            return find_head(buffer, HEAD, *args), None
        except ProtocolError as exc:
            return None, exc

    incremental, failure = outcome(scanned)
    full, full_failure = outcome()
    assert (incremental, getattr(failure, "status", None)) == (
        full,
        getattr(full_failure, "status", None),
    ), f"find_head from {scanned} disagrees with a full scan"
    if failure is not None:
        raise failure
    return incremental


def ours(data: bytes, cuts: list[int]):
    pieces = deque(
        data[a:b] for a, b in zip([0, *cuts], [*cuts, len(data)], strict=True) if b > a
    )
    received = 0

    def recv(size: int) -> bytes:
        nonlocal received
        if not pieces:
            return b""
        piece = pieces.popleft()
        if len(piece) > size:
            pieces.appendleft(piece[size:])
            piece = piece[:size]
        received += len(piece)
        return piece

    source = BufferedSource(recv)
    requests, starts = [], []
    try:
        while True:
            scanned = 0
            start = received - len(source.buffer)
            while (span := _find(source.buffer, scanned)) is None:
                scanned = len(source.buffer)
                if not source.receive_into_buffer():
                    return requests, starts, ("end", start)
            starts.append(start)
            head = parse_request_head(bytes(source.buffer[span[0] : span[1]]), HEAD)
            del source.buffer[: span[1]]
            if head.chunked:
                reader = ChunkedReader(source, BODY)
            else:
                reader = LengthReader(source, head.content_length or 0)
            body = reader.read()
            headers = tuple((name.lower(), value) for name, value in head.headers)
            requests.append((head.method, head.target, headers, body))
            if head.must_close or not head.keep_alive:
                return requests, starts, ("close",)
    except ProtocolError as exc:
        return requests, starts, ("refused", exc.status.value, exc.detail)
    except BodyError as exc:
        return requests, starts, ("body", str(exc))


def theirs(data: bytes):
    conn = h11.Connection(h11.SERVER, max_incomplete_event_size=HEAD.max_head_bytes)
    conn.receive_data(data)
    conn.receive_data(b"")
    requests = []
    request, body = None, b""
    try:
        while True:
            event = conn.next_event()
            if isinstance(event, h11.Request):
                request, body = event, b""
            elif isinstance(event, h11.Data):
                body += event.data
            elif isinstance(event, h11.EndOfMessage):
                requests.append(
                    (
                        request.method.decode("latin-1"),
                        request.target.decode("latin-1"),
                        tuple(
                            (name.decode("latin-1"), value.decode("latin-1"))
                            for name, value in request.headers
                        ),
                        body,
                    )
                )
                conn.send(
                    h11.Response(status_code=200, headers=[("Content-Length", "0")])
                )
                conn.send(h11.EndOfMessage())
                if conn.our_state is h11.MUST_CLOSE:
                    return requests, ("close",)
                conn.start_next_cycle()
            else:
                return requests, ("end", type(event).__name__)
    except h11.RemoteProtocolError as exc:
        return requests, ("refused", str(exc))


OURS_STRICTER = {
    "obsolete line folding": "obs-fold",
    "malformed Host": "host-syntax",
    "unsupported expectation": "expect",
    "unsupported request-target form": "target-form",
    "malformed request-target": "ctl-in-target",
    "control character in header field value": "ctl-in-field",
    "malformed Content-Length": "content-length-digits",
    "Transfer-Encoding in an HTTP/1.0 request": "te-on-http10",
    "only HTTP/1.x is supported": "http-major-version",
    "CONNECT is not supported": "connect",
    "NUL in request path": "encoded-nul",
    "too many empty lines before the request line": "leading-empty-lines",
    "chunked framing requires CRLF": "chunk-bare-lf",
    "malformed chunk size": "chunk-size",
    "chunk framing line too long": "chunk-line-limit",
    "chunked trailer section too large": "trailer-limit",
}


def _visible(text: str) -> bool:
    return all("\x21" <= c <= "\x7e" for c in text)


def _chunked_parts(segment: bytes) -> tuple[bytes, list[bytes], bytes, bytes] | None:
    match = re.search(rb"\r?\n\r?\n", segment)
    if match is None:
        return None
    head, rest = segment[: match.end()], segment[match.end() :]
    lines = []
    while True:
        line, sep, rest = rest.partition(b"\n")
        size = re.match(rb"[0-9A-Fa-f]+", line)
        if not sep or not size:
            return None
        lines.append(line)
        if int(size.group(), 16) == 0:
            trailers = []
            while True:
                line, sep, rest = rest.partition(b"\n")
                if not sep:
                    return None
                if not line.rstrip(b"\r"):
                    return head, lines, b"\n".join(trailers), rest
                trailers.append(line)
        data_and_crlf = int(size.group(), 16) + 2
        lines.append(rest[:data_and_crlf])
        rest = rest[data_and_crlf:]


def _rebuilt(head: bytes, lines: list[bytes], after: bytes, clean_ext: bool) -> bytes:
    out = []
    for index, line in enumerate(lines):
        if index % 2 == 0 and clean_ext:
            line = re.match(rb"[0-9A-Fa-f]+", line).group() + b"\r"
        out.append(line if index % 2 else line + b"\n")
    return head + b"".join(out) + b"\r\n" + after


def _accepts_as(segment: bytes, request: tuple) -> bool:
    their_requests, _ = theirs(segment)
    return bool(their_requests) and _comparable(their_requests[0]) == _comparable(
        request
    )


def _h11_stricter(message: str, request: tuple, segment: bytes) -> str | None:
    _method, target, headers, _body = request
    if segment[:1] in (b"\r", b"\n"):
        stripped = segment.lstrip(b"\r\n")
        if _accepts_as(stripped, request):
            return "leading-empty-lines"
        their_requests, outcome = theirs(stripped)
        if their_requests or outcome[0] != "refused":
            return None
        inner = _h11_stricter(outcome[1], request, stripped)
        return inner and f"leading-empty-lines, {inner}"
    if message.startswith("illegal request line") and not _visible(target):
        return "obs-text-target"
    if not any(name == "transfer-encoding" for name, _ in headers):
        return None
    parts = _chunked_parts(segment)
    if parts is None:
        return None
    head, lines, trailers, after = parts
    if trailers.strip(b"\r\n") and _accepts_as(
        _rebuilt(head, lines, after, clean_ext=False), request
    ):
        return "trailer-fields"
    if _accepts_as(_rebuilt(head, lines, after, clean_ext=True), request):
        return "chunk-ext"
    return None


def _ours_stricter(
    outcome: tuple, previous: tuple | None, segment: bytes
) -> str | None:
    if outcome[0] == "refused":
        if outcome[2] == "an HTTP/1.1 request needs exactly one Host" and re.match(
            rb"[^\r\n]* HTTP/1\.[2-9]\r?\n", segment.lstrip(b"\r\n")
        ):
            return "future-minor-version"
        return OURS_STRICTER.get(outcome[2])
    if outcome[0] == "body":
        return OURS_STRICTER.get(outcome[1])
    if outcome[0] == "close" and previous is not None:
        headers = {name for name, _ in previous[2]}
        if {"content-length", "transfer-encoding"} <= headers:
            return "cl-te"
    return None


def _comparable(request: tuple) -> tuple:
    method, target, headers, body = request
    # h11 folds the transfer coding to lower case and collapses a repeated
    # Content-Length; the body is what the framing decided either way
    fields = tuple(
        (name, value.lower() if name == "transfer-encoding" else value)
        for name, value in headers
        if name != "content-length"
    )
    return method, target, fields, body


def divergence(data: bytes, mine, other) -> str | None:
    requests, starts, outcome = mine
    their_requests, their_outcome = other
    shared = min(len(requests), len(their_requests))
    for index in range(shared):
        assert _comparable(requests[index]) == _comparable(their_requests[index]), (
            f"request {index + 1} parsed differently:\n"
            f"  ours  {requests[index]!r}\n  h11   {their_requests[index]!r}"
        )
    if len(requests) == len(their_requests):
        return ""
    if len(requests) < len(their_requests):
        segment = data[starts[shared] :] if shared < len(starts) else b""
        return _ours_stricter(outcome, requests[-1] if requests else None, segment)
    if their_outcome[0] != "refused":
        return None
    return _h11_stricter(their_outcome[1], requests[shared], data[starts[shared] :])


def _check(rng: random.Random, data: bytes) -> str:
    whole = ours(data, [])
    if len(data) > 1:
        cuts = sorted({rng.randrange(1, len(data)) for _ in range(rng.randint(1, 6))})
        assert ours(data, cuts) == whole, f"cut at {cuts}, the result changed"
    if len(data) < 300 and rng.random() < 0.05:
        assert ours(data, list(range(1, len(data)))) == whole, (
            "fed a byte at a time, the result changed"
        )
    other = theirs(data)
    named = divergence(data, whole, other)
    assert named is not None, (
        f"ours and h11 disagree outside the allowlist:\n"
        f"  ours {whole[2]!r} after {len(whole[0])} request(s)\n"
        f"  h11  {other[1]!r} after {len(other[0])} request(s)"
    )
    return named


def test_the_corpus_parses_as_h11_parses_it():
    for request in CORPUS:
        mine, other = ours(request, []), theirs(request)
        assert mine[2][0] in ("end", "close"), mine
        assert [_comparable(r) for r in mine[0]] == [_comparable(r) for r in other[0]]


def test_mutated_requests_keep_the_parser_invariants_and_agree_with_h11():
    rng = random.Random(SEED)
    seen = collections.Counter()
    for index in range(CASES):
        data = mutate(rng, pipeline(rng))
        try:
            seen[_check(rng, data)] += 1
        except AssertionError as exc:
            pytest.fail(
                f"case {index}, ODOO_TRANSPORT_FUZZ_SEED={SEED}: {exc}\n  input {data!r}",
                pytrace=False,
            )
        except Exception as exc:
            pytest.fail(
                f"case {index}, ODOO_TRANSPORT_FUZZ_SEED={SEED}: "
                f"{type(exc).__name__} escaped the parser: {exc}\n  input {data!r}",
                pytrace=False,
            )
    assert CASES // 2 < seen[""] < CASES, (
        f"the mutator lost its reach: {seen['']} of {CASES} cases parsed as h11 parses them"
    )


def _converse(port: int, payload: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port)) as sock:
        sock.settimeout(5)
        try:
            sock.sendall(payload)
            sock.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        buf = b""
        try:
            while chunk := sock.recv(65536):
                buf += chunk
        except TimeoutError:
            buf += STILL_OPEN
        except ConnectionResetError:
            pass
    return buf


def _echo(environ, start_response):
    body = environ["wsgi.input"].read()
    out = b"%d" % len(body)
    start_response("200 OK", [("Content-Length", str(len(out)))])
    return [out]


def test_mutated_pipelines_never_get_a_500_or_hang_a_live_server(caplog):
    rng = random.Random(SEED + 1)
    statuses = collections.Counter()
    with (
        caplog.at_level(logging.ERROR, logger="odoo.service.server"),
        serving(_echo) as srv,
    ):
        for index in range(LIVE_CASES):
            data = mutate(rng, pipeline(rng))
            raw = _converse(srv.server_port, data)
            assert not raw.endswith(STILL_OPEN), f"case {index} hung: {data!r}"
            codes = re.findall(rb"(?:^|\r\n)HTTP/1\.1 ([0-9]{3}) ", raw)
            assert b"500" not in codes, f"case {index} got a 500: {data!r}\n{raw!r}"
            statuses.update(codes)
        deadline = time.monotonic() + 2
        while srv.busy_workers and time.monotonic() < deadline:
            time.sleep(0.01)
        assert srv.busy_workers == 0
    assert not caplog.records, [r.getMessage() for r in caplog.records]
    assert statuses[b"200"] and statuses[b"400"], statuses
