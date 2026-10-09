import time
from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import dumps_bytes as json_dumps_bytes

try:
    from websocket import ABNF
    from websocket._abnf import VALID_CLOSE_STATUS
    from websocket._exceptions import WebSocketProtocolException
except ImportError:
    pass

from odoo.tests import common
from odoo.tests.common import BaseCase

from ..websocket import CloseCode, Opcode, RateLimitExceededError, Websocket
from .common import WebsocketCase
from .test_websocket_protocol import _client_frame


@common.tagged("-at_install", "post_install")
class TestRateLimiterUnit(BaseCase):
    BURST = 4
    DELAY = 1.0

    def _make_ws(self, clock):
        ws = Websocket.__new__(Websocket)
        ws._clock = clock
        ws.RL_DELAY = self.DELAY
        ws.RL_BURST = self.BURST
        ws.RL_CONTROL_FACTOR = Websocket.RL_CONTROL_FACTOR
        ws._data_frames_due = 0.0
        ws._control_frames_due = 0.0
        return ws

    def test_burst_is_allowed_then_blocks_within_the_window(self):
        now = [0.0]
        ws = self._make_ws(lambda: now[0])
        for _ in range(self.BURST):
            ws._limit_rate(Opcode.TEXT)
        with self.assertRaises(RateLimitExceededError):
            ws._limit_rate(Opcode.TEXT)

    def test_the_budget_refills_one_frame_per_interval(self):
        now = [0.0]
        ws = self._make_ws(lambda: now[0])
        for _ in range(self.BURST):
            ws._limit_rate(Opcode.TEXT)
        now[0] += self.DELAY
        ws._limit_rate(Opcode.TEXT)
        with self.assertRaises(RateLimitExceededError):
            ws._limit_rate(Opcode.TEXT)

    def test_respecting_the_rate_never_blocks(self):
        now = [0.0]
        ws = self._make_ws(lambda: now[0])
        for _ in range(self.BURST * 3):
            ws._limit_rate(Opcode.TEXT)
            now[0] += self.DELAY

    def test_control_frames_use_a_separate_larger_budget(self):
        now = [0.0]
        ws = self._make_ws(lambda: now[0])
        for _ in range(self.BURST):
            ws._limit_rate(Opcode.TEXT)
        for _ in range(self.BURST * Websocket.RL_CONTROL_FACTOR):
            ws._limit_rate(Opcode.PING)
        with self.assertRaises(RateLimitExceededError):
            ws._limit_rate(Opcode.PING)


@common.tagged("post_install", "-at_install")
class TestWebsocketRateLimiting(WebsocketCase):
    def setUp(self):
        super().setUp()
        self.startPatcher(patch.object(Websocket, "RL_BURST", 4))
        self.startPatcher(patch.object(Websocket, "RL_DELAY", 0.05))

    def assert_alive(self, ws):
        ws.ping()
        opcode, _frame = ws.recv_data_frame(control_frame=True)
        self.assertEqual(opcode, ABNF.OPCODE_PONG)

    def assert_rate_limited(self, ws):
        if 1013 not in VALID_CLOSE_STATUS:
            with self.assertRaises(WebSocketProtocolException) as cm:
                self.assert_close_with_code(ws, CloseCode.TRY_LATER)
            self.assertEqual(str(cm.exception), "Invalid close opcode.")
        else:
            self.assert_close_with_code(ws, CloseCode.TRY_LATER)

    def test_rate_limiting_base_ok(self):
        ws = self.websocket_connect()
        for _ in range(Websocket.RL_BURST + 1):
            ws.send(json_dumps({"event_name": "test_rate_limiting"}))
            time.sleep(Websocket.RL_DELAY * 1.25)
        self.assert_alive(ws)

    def _flood(self, ws, opcode, count, payload=b""):
        # one write, read in one go: the bucket refills while frames trickle
        # in, so a flood sent frame by frame on a busy machine can stay under
        # the limit; the exact burst is pinned against a fake clock above
        ws.sock.sendall(b"".join(_client_frame(opcode, payload) for _ in range(count)))

    def test_rate_limiting_base_ko(self):
        ws = self.websocket_connect()
        message = json_dumps_bytes({"event_name": "test_rate_limiting"})
        self._flood(ws, Opcode.TEXT, Websocket.RL_BURST * 4, message)
        self.assert_rate_limited(ws)

    def test_rate_limiting_opening_burst(self):
        ws = self.websocket_connect()

        for _ in range(Websocket.RL_BURST // 2):
            ws.send(json_dumps({"event_name": "test_rate_limiting"}))

        for _ in range(Websocket.RL_BURST):
            time.sleep(Websocket.RL_DELAY * 2)
            ws.send(json_dumps({"event_name": "test_rate_limiting"}))

        self.assert_alive(ws)

    def test_rate_limiting_start_ok_end_ko(self):
        ws = self.websocket_connect()

        for _ in range(Websocket.RL_BURST + 1):
            ws.send(json_dumps({"event_name": "test_rate_limiting"}))
            time.sleep(Websocket.RL_DELAY)

        message = json_dumps_bytes({"event_name": "test_rate_limiting"})
        self._flood(ws, Opcode.TEXT, Websocket.RL_BURST * 4, message)
        self.assert_rate_limited(ws)

    def test_control_frames_do_not_count_against_data_budget(self):
        ws = self.websocket_connect()
        for _ in range(Websocket.RL_BURST * 2):
            ws.ping()
            opcode, _frame = ws.recv_data_frame(control_frame=True)
            self.assertEqual(opcode, ABNF.OPCODE_PONG)
        self.assert_alive(ws)

    def test_continuation_frames_do_not_count_against_data_budget(self):
        ws = self.websocket_connect()
        message = json_dumps_bytes({"event_name": "test_rate_limiting"})
        fragments = [message[i : i + 2] for i in range(0, len(message), 2)]
        self.assertGreater(len(fragments), Websocket.RL_BURST)
        ws.sock.sendall(_client_frame(Opcode.TEXT, fragments[0], fin=False))
        for fragment in fragments[1:-1]:
            ws.sock.sendall(_client_frame(Opcode.CONTINUE, fragment, fin=False))
        ws.sock.sendall(_client_frame(Opcode.CONTINUE, fragments[-1], fin=True))
        self.assert_alive(ws)

    def test_control_frame_flood_is_rate_limited(self):
        ws = self.websocket_connect()
        self._flood(
            ws, Opcode.PING, Websocket.RL_BURST * Websocket.RL_CONTROL_FACTOR * 4
        )
        self.assert_rate_limited(ws)
