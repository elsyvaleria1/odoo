import base64
import os
import socket
import struct
import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from werkzeug.exceptions import BadRequest, ServiceUnavailable

from odoo.db import PoolError
from odoo.http import MemorySessionStore, Session, SessionExpiredException
from odoo.libs.json import dumps as json_dumps
from odoo.tests.common import HOST, TEST_CURSOR_COOKIE_NAME, BaseCase, tagged

try:
    from websocket import ABNF, WebSocketConnectionClosedException
except ImportError:
    ABNF = WebSocketConnectionClosedException = None

from .. import websocket as websocket_module
from ..tools.websocket_codec import FrameParser, encode_frame
from ..websocket import (
    MAX_TRY_ON_POOL_ERROR,
    CloseCode,
    CloseFrame,
    ConnectionClosedError,
    ConnectionState,
    Frame,
    InvalidCloseCodeError,
    NotificationDispatchState,
    Opcode,
    PayloadTooLargeError,
    ProtocolError,
    TimeoutManager,
    UpgradeRequired,
    Websocket,
    WebsocketConnectionHandler,
    _follow_session_chain,
    acquire_cursor,
)
from .common import WebsocketCase


class _ManualClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


class _FakeSocket:
    def __init__(self, chunks=()):
        self._chunks = list(chunks)
        self.sent = bytearray()

    @property
    def exhausted(self):
        return not self._chunks

    def recv(self, n):
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        if len(chunk) > n:
            chunk, rest = chunk[:n], chunk[n:]
            self._chunks.insert(0, rest)
        return chunk

    def sendall(self, data):
        self.sent.extend(data)

    def send(self, data):
        self.sent.extend(data)
        return len(data)


class _StallingSocket:
    def __init__(self, header):
        self._header = bytearray(header)
        self.sent = bytearray()
        self.recv_calls = 0

    def recv(self, n):
        self.recv_calls += 1
        if self._header:
            chunk = bytes(self._header[:n])
            del self._header[:n]
            return chunk
        return b"\x00"

    def sendall(self, data):
        self.sent.extend(data)


def _client_frame(
    opcode, payload=b"", *, fin=True, rsv1=False, masked=True, seven_bit_len=None
):
    b0 = (0x80 if fin else 0) | (0x40 if rsv1 else 0) | int(opcode)
    out = bytearray([b0])
    length = len(payload) if seven_bit_len is None else seven_bit_len
    mask_bit = 0x80 if masked else 0
    if length < 126:
        out.append(mask_bit | length)
    elif length < 65536:
        out.append(mask_bit | 126)
        out += struct.pack("!H", length)
    else:
        out.append(mask_bit | 127)
        out += struct.pack("!Q", length)
    if masked:
        out += b"\x00\x00\x00\x00"
    out += payload
    return bytes(out)


def _masked_client_frame(opcode, payload, mask=b"\x37\xfa\x21\x3d", *, fin=True):
    head = bytearray([(0x80 if fin else 0) | int(opcode)])
    if len(payload) < 126:
        head.append(0x80 | len(payload))
    elif len(payload) < 65536:
        head += bytes([0x80 | 126]) + struct.pack("!H", len(payload))
    else:
        head += bytes([0x80 | 127]) + struct.pack("!Q", len(payload))
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return bytes(head) + mask + masked


def _wire_splits(data):
    yield [data]
    yield [data[i : i + 1] for i in range(len(data))]
    for cut in range(1, len(data)):
        yield [data[:cut], data[cut:]]


@tagged("-at_install", "post_install")
class TestHandshakeValidation(BaseCase):
    def _valid_headers(self):
        return {
            "connection": "Upgrade",
            "host": "localhost:8069",
            "sec-websocket-key": base64.b64encode(b"0123456789abcdef").decode(),
            "sec-websocket-version": "13",
            "upgrade": "websocket",
            "origin": "http://localhost:8069",
        }

    def test_valid_handshake_succeeds(self):
        WebsocketConnectionHandler._assert_handshake_validity(self._valid_headers())

    def test_missing_required_header(self):
        for header in WebsocketConnectionHandler._REQUIRED_HANDSHAKE_HEADERS:
            headers = self._valid_headers()
            del headers[header]
            with self.assertRaises(BadRequest, msg=f"Missing {header!r} should raise"):
                WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_origin_is_not_a_required_header(self):
        self.assertNotIn(
            "origin", WebsocketConnectionHandler._REQUIRED_HANDSHAKE_HEADERS
        )
        headers = self._valid_headers()
        del headers["origin"]
        WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_empty_required_header_rejected(self):
        for header in WebsocketConnectionHandler._REQUIRED_HANDSHAKE_HEADERS:
            headers = self._valid_headers()
            headers[header] = ""
            with self.assertRaises(
                (BadRequest, UpgradeRequired), msg=f"Empty {header!r} should raise"
            ):
                WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_upgrade_required_lists_versions_comma_separated(self):
        headers = dict(UpgradeRequired().get_headers())
        self.assertEqual(
            headers["Sec-WebSocket-Version"],
            ", ".join(sorted(WebsocketConnectionHandler.SUPPORTED_VERSIONS)),
        )
        self.assertNotIn(";", headers["Sec-WebSocket-Version"])

    def test_wrong_upgrade_value(self):
        headers = self._valid_headers()
        headers["upgrade"] = "h2c"
        with self.assertRaises(BadRequest):
            WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_wrong_connection_value(self):
        headers = self._valid_headers()
        headers["connection"] = "keep-alive"
        with self.assertRaises(BadRequest):
            WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_unsupported_version(self):
        headers = self._valid_headers()
        headers["sec-websocket-version"] = "8"
        with self.assertRaises(UpgradeRequired):
            WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_key_not_valid_base64(self):
        headers = self._valid_headers()
        headers["sec-websocket-key"] = "not!valid!base64"
        with self.assertRaises(BadRequest):
            WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_key_wrong_decoded_length(self):
        headers = self._valid_headers()
        headers["sec-websocket-key"] = base64.b64encode(b"short").decode()
        with self.assertRaises(BadRequest):
            WebsocketConnectionHandler._assert_handshake_validity(headers)

    def test_handshake_response_has_correct_status(self):
        headers = self._valid_headers()
        response = WebsocketConnectionHandler._get_handshake_response(headers)
        self.assertEqual(response.status_code, 101)
        self.assertEqual(response.headers["Upgrade"], "websocket")
        self.assertEqual(response.headers["Connection"], "Upgrade")
        self.assertIn("Sec-WebSocket-Accept", response.headers)


@tagged("-at_install", "post_install")
class TestFrameClasses(BaseCase):
    def test_frame_has_slots(self):
        frame = Frame(Opcode.TEXT, b"hello")
        self.assertFalse(hasattr(frame, "__dict__"))
        self.assertEqual(frame.opcode, Opcode.TEXT)
        self.assertEqual(frame.payload, b"hello")
        self.assertTrue(frame.fin)

    def test_frame_defaults(self):
        frame = Frame(Opcode.PING)
        self.assertEqual(frame.payload, b"")
        self.assertTrue(frame.fin)
        self.assertFalse(frame.rsv1)
        self.assertFalse(frame.rsv2)
        self.assertFalse(frame.rsv3)

    def test_close_frame_valid_code(self):
        frame = CloseFrame(CloseCode.CLEAN, "goodbye")
        self.assertEqual(frame.code, CloseCode.CLEAN)
        self.assertEqual(frame.reason, "goodbye")
        self.assertEqual(frame.opcode, Opcode.CLOSE)
        self.assertEqual(len(frame.payload), 2 + len(b"goodbye"))

    def test_close_frame_no_reason(self):
        frame = CloseFrame(CloseCode.GOING_AWAY, None)
        self.assertEqual(len(frame.payload), 2)

    def test_close_frame_invalid_code(self):
        with self.assertRaises(InvalidCloseCodeError):
            CloseFrame(9999, "bad code")

    def test_close_frame_reserved_code_accepted(self):
        frame = CloseFrame(4001, "custom")
        self.assertEqual(frame.code, 4001)

    def test_close_frame_has_slots(self):
        frame = CloseFrame(CloseCode.CLEAN, None)
        self.assertFalse(hasattr(frame, "__dict__"))

    def test_close_frame_reason_truncated(self):
        frame = CloseFrame(CloseCode.CLEAN, "x" * 500)
        self.assertEqual(len(frame.payload), 2 + CloseFrame.MAX_REASON_LENGTH)
        self.assertEqual(frame.reason, "x" * CloseFrame.MAX_REASON_LENGTH)

    def test_close_frame_reason_truncation_keeps_utf8_valid(self):
        frame = CloseFrame(CloseCode.CLEAN, "é" * 100)
        self.assertLessEqual(len(frame.payload), 125)
        self.assertEqual(frame.reason, "é" * 61)
        frame.payload[2:].decode("utf-8")


@tagged("-at_install", "post_install")
class TestFollowSessionChain(BaseCase):
    def setUp(self):
        super().setUp()
        self.store = MemorySessionStore(Session)
        patcher = patch.object(websocket_module.root, "session_store", self.store)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _stored(self):
        session = self.store.new()
        session["uid"] = None
        self.store.save(session)
        return session

    def test_direct_session_no_chain(self):
        session = self._stored()
        self.assertEqual(_follow_session_chain(session).sid, session.sid)

    def test_soft_rotations_are_followed_to_the_live_successor(self):
        session = self._stored()
        initial_sid = session.sid
        self.store.rotate(session, env=None, soft=True)
        self.store.rotate(session, env=None, soft=True)
        initial = self.store.get(initial_sid)
        self.assertEqual(_follow_session_chain(initial).sid, session.sid)

    def test_missing_session_raises(self):
        with self.assertRaises(SessionExpiredException):
            _follow_session_chain(self.store.new())

    def test_a_revoked_successor_raises(self):
        session = self._stored()
        initial_sid = session.sid
        self.store.rotate(session, env=None, soft=True)
        self.store.delete(session)
        with self.assertRaises(SessionExpiredException):
            _follow_session_chain(self.store.get(initial_sid))

    def test_a_successor_outside_the_family_raises(self):
        session = self._stored()
        stranger = self._stored()
        session["next_sid"] = stranger.sid
        self.store.save(session)
        with self.assertRaises(SessionExpiredException):
            _follow_session_chain(session)


@tagged("-at_install", "post_install")
class TestAcquireCursor(BaseCase):
    def test_succeeds_on_first_try(self):
        mock_cr = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cr)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cm

        with (
            patch("odoo.addons.bus.websocket.db_connect", return_value=mock_connection),
            patch("time.sleep"),
        ):
            with acquire_cursor("testdb") as cr:
                self.assertIs(cr, mock_cr)

    def test_retries_on_transient_pool_error(self):
        mock_cr = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cr)
        mock_cm.__exit__ = MagicMock(return_value=False)

        call_count = 0

        def cursor_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PoolError("pool exhausted")
            return mock_cm

        mock_connection = MagicMock()
        mock_connection.cursor.side_effect = cursor_side_effect

        with (
            patch("odoo.addons.bus.websocket.db_connect", return_value=mock_connection),
            patch("time.sleep"),
        ):
            with acquire_cursor("testdb") as cr:
                self.assertIs(cr, mock_cr)
        self.assertEqual(call_count, 2)

    def test_raises_after_max_retries(self):
        mock_connection = MagicMock()
        mock_connection.cursor.side_effect = PoolError("always busy")

        with (
            patch("odoo.addons.bus.websocket.db_connect", return_value=mock_connection),
            patch("time.sleep"),
        ):
            with self.assertRaises(PoolError):
                with acquire_cursor("testdb"):
                    pass  # pragma: no cover

    def test_no_backoff_sleep_after_final_attempt(self):
        mock_connection = MagicMock()
        mock_connection.cursor.side_effect = PoolError("always busy")

        with (
            patch("odoo.addons.bus.websocket.db_connect", return_value=mock_connection),
            patch("time.sleep") as mock_sleep,
        ):
            with self.assertRaises(PoolError):
                with acquire_cursor("testdb"):
                    pass  # pragma: no cover
        backoff_sleeps = [
            call for call in mock_sleep.call_args_list if call.args[0] > 0
        ]
        self.assertEqual(len(backoff_sleeps), MAX_TRY_ON_POOL_ERROR - 1)

    def test_pool_error_from_body_not_swallowed(self):
        mock_cr = MagicMock()
        mock_cm = MagicMock()
        mock_cm.__enter__ = MagicMock(return_value=mock_cr)
        mock_cm.__exit__ = MagicMock(return_value=False)
        mock_connection = MagicMock()
        mock_connection.cursor.return_value = mock_cm

        with (
            patch("odoo.addons.bus.websocket.db_connect", return_value=mock_connection),
            patch("time.sleep"),
        ):
            with self.assertRaises(PoolError):
                with acquire_cursor("testdb"):
                    raise PoolError("raised by caller body")
        self.assertEqual(mock_connection.cursor.call_count, 1)
        mock_cm.__exit__.assert_called_once()


@tagged("-at_install", "post_install")
class TestNotificationDispatchState(BaseCase):
    def _make_state(self, retention_sec=10, now=100.0):
        clock = _ManualClock(now)
        return NotificationDispatchState(retention_sec, clock=clock), clock

    def test_initialize_last_id_only_adopts_client_value_once(self):
        state, _clock = self._make_state()
        state.initialize_last_id(5)
        self.assertEqual(state.last_id, 5)
        state.initialize_last_id(99)
        self.assertEqual(state.last_id, 5)

    def test_dispatched_ids_are_held_as_ignore_ids(self):
        state, _clock = self._make_state()
        state.record_dispatched([3, 7])
        self.assertEqual(state.last_id, 0)
        self.assertEqual(state.ignore_ids, [3, 7])

    def test_out_of_order_lower_id_is_still_held(self):
        state, clock = self._make_state()
        state.record_dispatched([3, 7])
        clock.now = 101.0
        state.record_dispatched([6])
        self.assertEqual(state.ignore_ids, [3, 6, 7])
        self.assertEqual(state.last_id, 0)

    def test_last_id_advances_past_contiguous_expired_prefix(self):
        state, clock = self._make_state()
        state.record_dispatched([3, 6, 7])
        clock.now = 111.0
        state.record_dispatched([])
        self.assertEqual(state.last_id, 7)
        self.assertEqual(state.ignore_ids, [])

    def test_recent_low_id_blocks_trimming_of_older_higher_id(self):
        state, clock = self._make_state()
        state.record_dispatched([6])
        clock.now = 108.0
        state.record_dispatched([3])
        clock.now = 109.0
        state.record_dispatched([])
        self.assertEqual(state.last_id, 0)
        self.assertEqual(state.ignore_ids, [3, 6])
        clock.now = 200.0
        state.record_dispatched([])
        self.assertEqual(state.last_id, 6)
        self.assertEqual(state.ignore_ids, [])

    def test_history_is_capped(self):
        state, _clock = self._make_state()
        with patch.object(NotificationDispatchState, "MAX_HISTORY_LENGTH", 4):
            state.record_dispatched([1, 2, 3, 4])
            self.assertEqual(state.ignore_ids, [1, 2, 3, 4])
            with self.assertLogs("odoo.addons.bus.websocket", level="DEBUG") as log:
                state.record_dispatched([5, 6])
            self.assertIn("history capped", log.output[0])
            self.assertEqual(state.ignore_ids, [3, 4, 5, 6])
            self.assertEqual(state.last_id, 2)

    def test_cap_does_not_bite_below_limit(self):
        state, clock = self._make_state()
        with patch.object(NotificationDispatchState, "MAX_HISTORY_LENGTH", 4):
            state.record_dispatched([1, 2, 3])
            clock.now = 105.0
            state.record_dispatched([4])
            self.assertEqual(state.ignore_ids, [1, 2, 3, 4])
            self.assertEqual(state.last_id, 0)


@tagged("-at_install", "post_install")
class TestSessionValidityCache(BaseCase):
    def _make_ws(self, clock, session):
        ws = Websocket.__new__(Websocket)
        ws._clock = clock
        ws._db = "db"
        ws._session = session
        ws._session_validated_until = 0.0
        ws._validated_session_sid = None
        ws._waiting_for_dispatch = True
        ws._channels = frozenset()
        ws._dispatch_state = NotificationDispatchState(10, clock=clock)
        ws.SESSION_VALIDITY_JITTER = 0
        return ws

    @contextmanager
    def _dispatch_env(self, check_session_return=True):
        env = MagicMock()
        env.__getitem__.return_value._poll_batch.return_value = ([], False)

        @contextmanager
        def fake_acquire_cursor(db):
            yield MagicMock()

        with (
            patch(
                "odoo.addons.bus.websocket._follow_session_chain",
                side_effect=lambda session: session,
            ),
            patch(
                "odoo.addons.bus.websocket.is_session_valid",
                return_value=check_session_return,
            ) as check_session_mock,
            patch("odoo.addons.bus.websocket.acquire_cursor", fake_acquire_cursor),
            patch.object(Websocket, "new_env", return_value=env),
        ):
            yield check_session_mock

    def test_cache_expires_after_ttl(self):
        clock = _ManualClock(100.0)
        session = MagicMock(sid="sid-A", uid=1, db="testdb")
        ws = self._make_ws(clock, session)
        with self._dispatch_env() as check_session_mock:
            ws._dispatch_bus_notifications()
            self.assertEqual(check_session_mock.call_count, 1)
            clock.now += Websocket.SESSION_VALIDITY_TTL - 1
            ws._dispatch_bus_notifications()
            self.assertEqual(check_session_mock.call_count, 1)
            clock.now += 1
            ws._dispatch_bus_notifications()
            self.assertEqual(check_session_mock.call_count, 2)

    def test_session_swap_forces_revalidation_before_ttl(self):
        clock = _ManualClock(100.0)
        session = MagicMock(sid="sid-A", uid=1, db="testdb")
        ws = self._make_ws(clock, session)
        with self._dispatch_env() as check_session_mock:
            ws._dispatch_bus_notifications()
            self.assertEqual(check_session_mock.call_count, 1)
            ws._session = MagicMock(sid="sid-B", uid=1, db="testdb")
            ws._dispatch_bus_notifications()
            self.assertEqual(check_session_mock.call_count, 2)

    def test_invalid_session_raises_session_expired(self):
        clock = _ManualClock(100.0)
        session = MagicMock(sid="sid-A", uid=1, db="testdb")
        ws = self._make_ws(clock, session)
        with self._dispatch_env(check_session_return=False):
            with self.assertRaises(SessionExpiredException):
                ws._dispatch_bus_notifications()

    def test_validity_is_spread_below_the_ttl(self):
        clock = _ManualClock(100.0)
        session = MagicMock(sid="sid-A", uid=1, db="testdb")
        horizons = set()
        with self._dispatch_env():
            for _ in range(50):
                ws = self._make_ws(clock, session)
                del ws.SESSION_VALIDITY_JITTER
                ws._dispatch_bus_notifications()
                horizons.add(ws._session_validated_until - clock.now)
        ttl, jitter = Websocket.SESSION_VALIDITY_TTL, Websocket.SESSION_VALIDITY_JITTER
        self.assertGreater(len(horizons), 1)
        self.assertTrue(all(ttl * (1 - jitter) <= h <= ttl for h in horizons))

    def test_waiting_for_dispatch_reset_even_without_notifications(self):
        clock = _ManualClock(100.0)
        session = MagicMock(sid="sid-A", uid=1, db="testdb")
        ws = self._make_ws(clock, session)
        with self._dispatch_env():
            ws._dispatch_bus_notifications()
        self.assertFalse(ws._waiting_for_dispatch)


def _make_receiving_ws(chunks=(), *, clock=None):
    sock = _FakeSocket(chunks)
    ws = Websocket(sock, MagicMock(db="db"), {}, clock=clock or time.monotonic)
    ws._parser = FrameParser(ws.MESSAGE_MAX_SIZE, lambda opcode: None)
    return ws, sock


def _read_all(ws, sock):
    messages = []
    while not sock.exhausted:
        messages.extend(ws._read_messages())
    return messages


@tagged("-at_install", "post_install")
class TestFrameParser(BaseCase):
    def _feed(self, parser, chunks):
        frames = []
        for chunk in chunks:
            frames.extend(parser.feed(chunk))
        return frames

    def test_header_is_announced_once_per_frame_wherever_it_is_cut(self):
        data = _client_frame(Opcode.TEXT, b"ab") + _client_frame(
            Opcode.PING, b"", fin=True
        )
        for chunks in _wire_splits(data):
            seen = []
            parser = FrameParser(1024, seen.append)
            frames = self._feed(parser, chunks)
            self.assertEqual([f.opcode for f in frames], [Opcode.TEXT, Opcode.PING])
            self.assertEqual(seen, [Opcode.TEXT, Opcode.PING])
            self.assertFalse(parser.mid_frame)

    def test_extended_lengths_survive_every_cut(self):
        for size in (125, 126, 65535, 65536):
            payload = bytes(range(256)) * (size // 256) + bytes(size % 256)
            data = _masked_client_frame(Opcode.BINARY, payload)
            for chunks in (
                [data],
                [data[:1], data[1:]],
                [data[:3], data[3:]],
                [data[:9], data[9:]],
                [data[:-1], data[-1:]],
            ):
                frames = self._feed(FrameParser(2**20), chunks)
                self.assertEqual(len(frames), 1, f"size {size}")
                self.assertEqual(frames[0].payload, payload, f"size {size}")

    def test_partial_frame_is_reported_mid_frame(self):
        data = _client_frame(Opcode.TEXT, b"hello")
        parser = FrameParser(1024)
        self.assertEqual(parser.feed(data[:-1]), [])
        self.assertTrue(parser.mid_frame)
        self.assertEqual(len(parser.feed(data[-1:])), 1)
        self.assertFalse(parser.mid_frame)

    def test_encoded_frames_carry_the_shortest_length_field(self):
        for size, header in ((125, 2), (126, 4), (65535, 4), (65536, 10)):
            data = encode_frame(Frame(Opcode.BINARY, b"x" * size))
            self.assertEqual(len(data), header + size)
            opcode, payload = _parse_server_frame(data)
            self.assertEqual(opcode, Opcode.BINARY)
            self.assertEqual(len(payload), size)

    def test_encoder_refuses_an_oversized_control_frame(self):
        with self.assertRaises(ProtocolError):
            encode_frame(Frame(Opcode.PING, b"x" * 126))


@tagged("-at_install", "post_install")
class TestFrameCodec(BaseCase):
    def test_decoded_frame_flags_are_boolean(self):
        for final in (False, True):
            for chunks in _wire_splits(_client_frame(Opcode.TEXT, b"hello", fin=final)):
                with self.subTest(final=final, chunks=len(chunks)):
                    parser = FrameParser(Websocket.MESSAGE_MAX_SIZE)
                    frames = [f for chunk in chunks for f in parser.feed(chunk)]
                    self.assertEqual(len(frames), 1)
                    frame = frames[0]
                    self.assertIs(frame.fin, final)
                    self.assertIs(frame.rsv1, False)
                    self.assertIs(frame.rsv2, False)
                    self.assertIs(frame.rsv3, False)
                    self.assertEqual(frame.payload, b"hello")

    def _assert_messages(self, data, expected):
        for chunks in _wire_splits(data):
            ws, sock = _make_receiving_ws(chunks)
            self.assertEqual(_read_all(ws, sock), expected, f"cut as {chunks!r}")

    def _assert_raises(self, exception, data, *, max_size=None):
        for chunks in _wire_splits(data):
            ws, sock = _make_receiving_ws(chunks)
            if max_size is not None:
                ws.MESSAGE_MAX_SIZE = max_size
                ws._parser = FrameParser(max_size)
            with self.assertRaises(exception, msg=f"cut as {chunks!r}"):
                _read_all(ws, sock)

    def test_single_text_frame(self):
        self._assert_messages(_client_frame(Opcode.TEXT, b"hello"), ["hello"])

    def test_fragmented_text_message_is_reassembled(self):
        data = _client_frame(Opcode.TEXT, b"Hello ", fin=False) + _client_frame(
            Opcode.CONTINUE, b"World", fin=True
        )
        self._assert_messages(data, ["Hello World"])

    def test_control_frame_interleaved_in_fragmented_message(self):
        data = (
            _client_frame(Opcode.TEXT, b"Hello ", fin=False)
            + _client_frame(Opcode.PING, b"ka", fin=True)
            + _client_frame(Opcode.CONTINUE, b"World", fin=True)
        )
        for chunks in _wire_splits(data):
            ws, sock = _make_receiving_ws(chunks)
            self.assertEqual(_read_all(ws, sock), ["Hello World"])
            self.assertTrue(sock.sent)
            self.assertEqual(sock.sent[0] & 0x0F, int(Opcode.PONG))

    def test_reserved_bit_set_raises(self):
        self._assert_raises(ProtocolError, _client_frame(Opcode.TEXT, b"x", rsv1=True))

    def test_unmasked_client_frame_raises(self):
        self._assert_raises(
            ProtocolError, _client_frame(Opcode.TEXT, b"x", masked=False)
        )

    def test_invalid_opcode_raises(self):
        self._assert_raises(ProtocolError, bytes([0x80 | 0x03, 0x80, 0, 0, 0, 0]))

    def test_oversized_control_frame_raises(self):
        self._assert_raises(
            ProtocolError, _client_frame(Opcode.CLOSE, b"", seven_bit_len=126)
        )

    def test_fragmented_control_frame_raises(self):
        self._assert_raises(ProtocolError, _client_frame(Opcode.PING, b"x", fin=False))

    def test_payload_too_large_single_frame_raises(self):
        frame = (
            bytes([0x80 | int(Opcode.TEXT), 0x80 | 127])
            + struct.pack("!Q", Websocket.MESSAGE_MAX_SIZE + 1)
            + b"\x00\x00\x00\x00"
        )
        self._assert_raises(PayloadTooLargeError, frame)

    def test_unexpected_top_level_continuation_raises(self):
        self._assert_raises(
            ProtocolError, _client_frame(Opcode.CONTINUE, b"x", fin=True)
        )

    def test_data_frame_where_continuation_expected_raises(self):
        data = _client_frame(Opcode.TEXT, b"a", fin=False) + _client_frame(
            Opcode.TEXT, b"b", fin=True
        )
        self._assert_raises(ProtocolError, data)

    def test_payload_too_large_during_reassembly_raises(self):
        data = _client_frame(Opcode.TEXT, b"12345", fin=False) + _client_frame(
            Opcode.CONTINUE, b"67890", fin=True
        )
        self._assert_raises(PayloadTooLargeError, data, max_size=8)

    def test_stalled_frame_is_abandoned_at_the_deadline(self):
        header = struct.pack("!BBH", 0x81, 0x80 | 126, 1000) + b"\x00\x00\x00\x00"
        sock = _StallingSocket(header)
        clock = _ManualClock()
        ws = Websocket(sock, MagicMock(db="db"), {}, clock=clock)
        ws._parser = FrameParser(ws.MESSAGE_MAX_SIZE, lambda opcode: None)

        original_recv = sock.recv

        def ticking_recv(n):
            clock.now += 1
            return original_recv(n)

        sock.recv = ticking_recv

        with self.assertRaises(ConnectionClosedError):
            while True:
                list(ws._read_messages())
                ws._check_frame_deadline()
        self.assertLess(sock.recv_calls, 1000)
        self.assertGreaterEqual(clock.now, Websocket.FRAME_RECEIVE_TIMEOUT)

    def test_frame_deadline_does_not_disturb_a_prompt_peer(self):
        clock = _ManualClock()
        for chunks in _wire_splits(_client_frame(Opcode.TEXT, b"hello")):
            ws, sock = _make_receiving_ws(chunks, clock=clock)
            self.assertEqual(_read_all(ws, sock), ["hello"])
            clock.now += Websocket.FRAME_RECEIVE_TIMEOUT * 2
            ws._check_frame_deadline()

    def test_truncated_frame_raises_connection_closed(self):
        truncated = _client_frame(Opcode.TEXT, b"hello")[:-3]
        for chunks in _wire_splits(truncated):
            ws, sock = _make_receiving_ws(chunks)
            self.assertEqual(_read_all(ws, sock), [])
            with self.assertRaises(ConnectionClosedError):
                ws._read_messages()

    def test_close_interleaved_in_fragmented_message_abandons_message(self):
        data = _client_frame(Opcode.TEXT, b"Hello ", fin=False) + _client_frame(
            Opcode.CLOSE, struct.pack("!H", CloseCode.CLEAN)
        )
        for chunks in _wire_splits(data):
            ws, sock = _make_receiving_ws(chunks)
            ws._terminate = MagicMock()
            self.assertEqual(_read_all(ws, sock), [])
            opcode, payload = _parse_server_frame(sock.sent)
            self.assertEqual(opcode, Opcode.CLOSE)
            self.assertEqual(struct.unpack("!H", payload[:2])[0], CloseCode.CLEAN)
            ws._terminate.assert_called_once()

    def test_data_frame_received_while_closing_is_discarded(self):
        for chunks in _wire_splits(_client_frame(Opcode.TEXT, b"late data")):
            ws, sock = _make_receiving_ws(chunks)
            ws.state = ConnectionState.CLOSING
            self.assertEqual(_read_all(ws, sock), [])


def _parse_server_frame(data):
    first_byte, second_byte = data[0], data[1]
    opcode = Opcode(first_byte & 0x0F)
    length = second_byte & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", data[2:4])[0]
        offset = 4
    elif length == 127:
        length = struct.unpack("!Q", data[2:10])[0]
        offset = 10
    return opcode, bytes(data[offset : offset + length])


@tagged("-at_install", "post_install")
class TestCloseFrameHandling(BaseCase):
    def _receive_close(self, payload):
        for chunks in _wire_splits(_client_frame(Opcode.CLOSE, payload)):
            ws, sock = _make_receiving_ws(chunks)
            ws._terminate = MagicMock()
            _read_all(ws, sock)
            yield ws, sock

    def _assert_close_answer(self, sock, expected_code, expected_reason=None):
        opcode, payload = _parse_server_frame(sock.sent)
        self.assertEqual(opcode, Opcode.CLOSE)
        self.assertEqual(struct.unpack("!H", payload[:2])[0], expected_code)
        if expected_reason is not None:
            self.assertEqual(payload[2:].decode(), expected_reason)

    def test_legal_close_is_echoed(self):
        payload = struct.pack("!H", CloseCode.CLEAN) + b"bye"
        for ws, sock in self._receive_close(payload):
            self._assert_close_answer(sock, CloseCode.CLEAN, "bye")
            ws._terminate.assert_called_once()

    def test_reserved_range_close_code_is_echoed(self):
        for _ws, sock in self._receive_close(struct.pack("!H", 4242)):
            self._assert_close_answer(sock, 4242)

    def test_invalid_close_code_answered_with_protocol_error(self):
        for bad_code in (999, 1005, 1006, 1015, 2999):
            for ws, sock in self._receive_close(struct.pack("!H", bad_code)):
                self._assert_close_answer(sock, CloseCode.PROTOCOL_ERROR)
                ws._terminate.assert_called_once()

    def test_one_byte_close_payload_answered_with_protocol_error(self):
        for _ws, sock in self._receive_close(b"\x01"):
            self._assert_close_answer(sock, CloseCode.PROTOCOL_ERROR)

    def test_invalid_utf8_close_reason_answered_with_inconsistent_data(self):
        payload = struct.pack("!H", CloseCode.CLEAN) + b"\xff\xfe"
        for _ws, sock in self._receive_close(payload):
            self._assert_close_answer(sock, CloseCode.INCONSISTENT_DATA)

    def test_empty_close_payload_answered_with_clean(self):
        for _ws, sock in self._receive_close(b""):
            self._assert_close_answer(sock, CloseCode.CLEAN)


@tagged("-at_install", "post_install")
class TestOpenConnection(BaseCase):
    def test_service_unavailable_when_websocket_disabled(self):
        request = MagicMock()
        with patch.object(
            WebsocketConnectionHandler, "websocket_allowed", return_value=False
        ):
            with self.assertRaises(ServiceUnavailable):
                WebsocketConnectionHandler.open_connection(request, "19.0-5")

    def test_public_configuration_runs_after_handshake_validation(self):
        request = MagicMock()
        with (
            patch.object(
                WebsocketConnectionHandler, "websocket_allowed", return_value=True
            ),
            patch.object(
                WebsocketConnectionHandler,
                "_get_handshake_response",
                side_effect=BadRequest("bad handshake"),
            ),
            patch.object(
                WebsocketConnectionHandler, "_handle_public_configuration"
            ) as public_config_mock,
        ):
            with (
                self.assertRaises(BadRequest),
                self.assertLogs("odoo.addons.bus.websocket", "WARNING") as logs,
            ):
                WebsocketConnectionHandler.open_connection(request, "19.0-5")
        public_config_mock.assert_not_called()
        self.assertEqual(
            [record.levelname for record in logs.records],
            ["WARNING"],
            "a client's bad handshake is not a server error",
        )


@tagged("-at_install", "post_install")
class TestTrustedOrigin(BaseCase):
    def _request(self, scheme, host):
        request = MagicMock()
        request.httprequest.scheme = scheme
        request.httprequest.host = host
        return request

    def test_matching_origin_is_trusted(self):
        request = self._request("http", "example.com:8069")
        self.assertTrue(
            WebsocketConnectionHandler._is_trusted_origin(
                "http://example.com:8069", request
            )
        )

    def test_default_port_is_normalized(self):
        request = self._request("https", "example.com")
        self.assertTrue(
            WebsocketConnectionHandler._is_trusted_origin(
                "https://example.com:443", request
            )
        )

    def test_mismatched_origin_is_not_trusted(self):
        request = self._request("http", "example.com:8069")
        self.assertFalse(
            WebsocketConnectionHandler._is_trusted_origin(
                "http://attacker.example.com", request
            )
        )

    def test_scheme_mismatch_is_not_trusted(self):
        request = self._request("https", "example.com")
        self.assertFalse(
            WebsocketConnectionHandler._is_trusted_origin("http://example.com", request)
        )

    def test_allowlisted_origin_is_trusted(self):
        request = self._request("http", "example.com:8069")
        with patch.dict(
            os.environ,
            {"ODOO_BUS_TRUSTED_ORIGINS": "https://cdn.example.com, http://x.test:9000"},
        ):
            self.assertTrue(
                WebsocketConnectionHandler._is_trusted_origin(
                    "http://x.test:9000", request
                )
            )
            self.assertFalse(
                WebsocketConnectionHandler._is_trusted_origin(
                    "http://not-listed.test", request
                )
            )


@tagged("-at_install", "post_install")
class TestControlCommandPriority(BaseCase):
    def test_queued_close_beats_pending_dispatch(self):
        sock = _FakeSocket()
        ws = Websocket(sock, MagicMock(db="db"), {})
        hub = MagicMock()
        hub.in_loop.return_value = True
        submitted = []
        hub.submit.side_effect = lambda job: submitted.append(job) or True
        ws._hub = hub
        ws._job = object()
        ws.trigger_notification_dispatching()
        self.assertTrue(ws._dispatch_pending, "the dispatch waits behind the job")
        ws.close(CloseCode.CLEAN)
        opcode, payload = _parse_server_frame(sock.sent)
        self.assertIs(opcode, Opcode.CLOSE)
        self.assertEqual(struct.unpack("!H", payload[:2])[0], CloseCode.CLEAN)
        ws._job_done()
        self.assertEqual(submitted, [], "the pending dispatch must not run after it")


@tagged("post_install", "-at_install")
class TestCloseCodesOverWire(WebsocketCase):
    def test_invalid_utf8_text_frame_closes_1007(self):
        ws = self.websocket_connect()
        ws.send(b"\xff\xfe\xfd", opcode=ABNF.OPCODE_TEXT)
        self.assert_close_with_code(ws, CloseCode.INCONSISTENT_DATA)

    def test_oversized_frame_closes_1009(self):
        self.startPatcher(patch.object(Websocket, "MESSAGE_MAX_SIZE", 1024))
        ws = self.websocket_connect()
        ws.send("x" * 2048)
        self.assert_close_with_code(ws, CloseCode.MESSAGE_TOO_BIG)

    def test_protocol_violation_closes_1002(self):
        ws = self.websocket_connect()
        ws.sock.sendall(_client_frame(Opcode.TEXT, b"x", rsv1=True))
        self.assert_close_with_code(ws, CloseCode.PROTOCOL_ERROR)

    def test_invalid_close_code_answered_with_1002(self):
        ws = self.websocket_connect()
        ws.sock.sendall(_client_frame(Opcode.CLOSE, struct.pack("!H", 999)))
        self.assert_close_with_code(ws, CloseCode.PROTOCOL_ERROR, "Invalid close code")

    def test_one_byte_close_payload_answered_with_1002(self):
        ws = self.websocket_connect()
        ws.sock.sendall(_client_frame(Opcode.CLOSE, b"\x01"))
        self.assert_close_with_code(
            ws, CloseCode.PROTOCOL_ERROR, "Malformed closing frame"
        )

    def test_legal_close_code_and_reason_echoed(self):
        ws = self.websocket_connect()
        ws.sock.sendall(
            _client_frame(Opcode.CLOSE, struct.pack("!H", CloseCode.CLEAN) + b"bye")
        )
        self.assert_close_with_code(ws, CloseCode.CLEAN, "bye")

    def test_malformed_envelope_keeps_connection_alive(self):
        self.startPatcher(patch.object(Websocket, "RL_BURST", 100))
        ws = self.websocket_connect()
        for message in ("not-json{", json_dumps(["top-level-list"]), json_dumps({})):
            with self.assertLogs(
                "odoo.addons.bus.websocket", level="WARNING"
            ) as capture:
                ws.send(message)
                ws.ping()
                ws.recv_data_frame(control_frame=True)
            self.assertTrue(
                any("Invalid websocket request" in line for line in capture.output),
                f"message {message!r} should be rejected with a warning",
            )
        ws.ping()
        opcode, _ = ws.recv_data_frame(control_frame=True)
        self.assertEqual(opcode, ABNF.OPCODE_PONG)

    def test_kill_now_terminates_without_close_handshake(self):
        ws = self.websocket_connect()
        server_ws = next(
            websocket
            for websocket in websocket_module._open_websockets()
            if websocket.state is ConnectionState.OPEN
        )
        server_ws.close(CloseCode.KILL_NOW)
        with self.assertRaises(WebSocketConnectionClosedException):
            ws.recv_data_frame(control_frame=True)

    def test_kick_all_sends_going_away(self):
        ws = self.websocket_connect()
        websocket_module._kick_all()
        self.assert_close_with_code(ws, CloseCode.GOING_AWAY)

    def test_server_pings_after_inactivity_timeout(self):
        self.startPatcher(patch.object(TimeoutManager, "INACTIVITY_TIMEOUT", 0))
        self.startPatcher(patch.object(TimeoutManager, "TIMEOUT", 0.2))
        ws = self.websocket_connect(ping_after_connect=False)
        opcode, _ = ws.recv_data_frame(control_frame=True)
        self.assertEqual(opcode, ABNF.OPCODE_PING)


@tagged("post_install", "-at_install")
class TestUpgradeAdoption(WebsocketCase):
    def _handshake(self):
        self.session = self.authenticate(None, None)
        key = base64.b64encode(os.urandom(16)).decode()
        origin = f"http://{HOST}:{self.http_port()}"
        cookie = (
            f"session_id={self.session.sid};"
            f"{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}"
        )
        return (
            f"GET /websocket?version={WebsocketConnectionHandler._VERSION} HTTP/1.1\r\n"
            f"Host: {HOST}:{self.http_port()}\r\nOrigin: {origin}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            f"Cookie: {cookie}\r\n\r\n"
        ).encode()

    def _read_frame(self, sock, buffer):
        while True:
            if len(buffer) >= 2 and len(buffer) >= 2 + (buffer[1] & 0x7F):
                opcode, payload = _parse_server_frame(buffer)
                return opcode, payload, buffer[2 + len(payload) :]
            buffer += sock.recv(4096)

    def test_frames_sent_behind_the_handshake_are_served(self):
        early_ping = _masked_client_frame(Opcode.PING, b"early")
        with socket.create_connection((HOST, self.http_port()), timeout=10) as sock:
            sock.sendall(self._handshake() + early_ping)
            received = b""
            while b"\r\n\r\n" not in received:
                received += sock.recv(4096)
            head, _, rest = received.partition(b"\r\n\r\n")
            self.assertTrue(head.startswith(b"HTTP/1.1 101"), head)
            opcode, payload, rest = self._read_frame(sock, rest)
            self.assertEqual(opcode, Opcode.PONG)
            self.assertEqual(payload, b"early")
            sock.sendall(
                _masked_client_frame(Opcode.CLOSE, struct.pack("!H", CloseCode.CLEAN))
            )
            opcode, payload, rest = self._read_frame(sock, rest)
            self.assertEqual(opcode, Opcode.CLOSE)
            self.assertEqual(struct.unpack("!H", payload[:2])[0], CloseCode.CLEAN)
        self.wait_remaining_websocket_connections()
