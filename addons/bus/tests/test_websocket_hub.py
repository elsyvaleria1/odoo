import os
import socket
import struct
import threading
import time
from unittest.mock import MagicMock, PropertyMock, patch

from odoo.http import SessionExpiredException
from odoo.libs.json import loads as json_loads
from odoo.service.metrics import render_prometheus_exposition
from odoo.service.server import WebsocketServer
from odoo.tests import BaseCase, tagged

try:
    from websocket import WebSocketBadStatusException
except ImportError:
    WebSocketBadStatusException = None

from .. import websocket as websocket_module
from ..models.bus import dispatch
from ..tools.websocket_hub import DbExecutor, WebsocketHub
from ..websocket import (
    CloseCode,
    ConnectionGauge,
    ConnectionState,
    Opcode,
    TimeoutManager,
    Websocket,
)
from .common import WebsocketCase
from .test_websocket_protocol import _masked_client_frame, _parse_server_frame


def _wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class _Peer:
    def __init__(self, sock):
        self.sock = sock
        self.sock.settimeout(5)
        self.buffer = b""

    def send(self, opcode, payload=b"", *, fin=True):
        self.sock.sendall(_masked_client_frame(opcode, payload, fin=fin))

    def frame(self):
        while True:
            if len(self.buffer) >= 2:
                length = self.buffer[1] & 0x7F
                head = 2 + {126: 2, 127: 8}.get(length, 0)
                if len(self.buffer) >= head:
                    if length == 126:
                        length = struct.unpack("!H", self.buffer[2:4])[0]
                    elif length == 127:
                        length = struct.unpack("!Q", self.buffer[2:10])[0]
                    if len(self.buffer) >= head + length:
                        opcode, payload = _parse_server_frame(self.buffer)
                        self.buffer = self.buffer[head + length :]
                        return opcode, payload
            data = self.sock.recv(65536)
            if not data:
                raise ConnectionError("server closed")
            self.buffer += data


@tagged("-at_install", "post_install")
class TestWebsocketHub(BaseCase):
    def setUp(self):
        super().setUp()
        self.hub = WebsocketHub(db_threads=lambda: 2)
        self.served = []
        self.release = threading.Event()
        self.release.set()
        self.running = 0
        self.max_running = 0
        self.torn_down = threading.Event()
        test = self

        def message_job(websocket, message):
            test.running += 1
            test.max_running = max(test.max_running, test.running)
            try:
                test.release.wait(5)
                test.served.append(message)
            finally:
                test.running -= 1

        def teardown(websocket):
            test.torn_down.set()

        self.startPatcher(patch.object(Websocket, "_message_job", message_job))
        self.startPatcher(patch.object(Websocket, "_teardown", teardown))
        self.startPatcher(patch.object(Websocket, "RL_BURST", 1000))
        self.startPatcher(patch("odoo.addons.bus.websocket._hub", self.hub))
        self.addCleanup(self.hub.stop, 0.5, CloseCode.GOING_AWAY)

    def _connect(self, buffered=b"", **kwargs):
        server, client = socket.socketpair()
        self.addCleanup(client.close)
        gauge = ConnectionGauge(0)
        gauge.reserve()
        websocket = Websocket(server, MagicMock(db="db"), {}, gauge=gauge, **kwargs)
        websocket._adopt(server, buffered, ("127.0.0.1", 0))
        self.assertTrue(_wait_until(lambda: websocket.fd in self.hub.connections))
        return websocket, _Peer(client), gauge

    def test_one_loop_thread_serves_every_connection(self):
        before = threading.active_count()
        pairs = [self._connect() for _ in range(20)]
        for _ws, peer, _gauge in pairs:
            peer.send(Opcode.PING, b"hi")
        for _ws, peer, _gauge in pairs:
            self.assertEqual(peer.frame(), (Opcode.PONG, b"hi"))
        self.assertLessEqual(threading.active_count() - before, 1)

    def test_the_kernel_send_buffer_is_capped(self):
        ws, _peer, _gauge = self._connect()
        sndbuf = ws.sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
        self.assertLessEqual(sndbuf, 2 * Websocket.SEND_BUFFER)

    def test_bytes_handed_over_with_the_socket_are_served(self):
        _ws, peer, _gauge = self._connect(
            buffered=_masked_client_frame(Opcode.PING, b"early")
        )
        self.assertEqual(peer.frame(), (Opcode.PONG, b"early"))

    def test_close_handshake_releases_the_connection(self):
        ws, peer, gauge = self._connect()
        peer.send(Opcode.CLOSE, struct.pack("!H", CloseCode.CLEAN) + b"bye")
        opcode, payload = peer.frame()
        self.assertEqual(opcode, Opcode.CLOSE)
        self.assertEqual(payload, struct.pack("!H", CloseCode.CLEAN) + b"bye")
        self.assertTrue(_wait_until(lambda: ws.lingering), "half-closed, reading")
        self.assertEqual(peer.sock.recv(1), b"", "the server's side is shut")
        peer.sock.close()
        self.assertTrue(_wait_until(lambda: gauge.count == 0))
        self.assertNotIn(ws.fd, self.hub.connections)
        self.assertIs(ws.state, ConnectionState.CLOSED)
        self.assertTrue(self.torn_down.wait(5), "the close hooks run after the close")

    def test_a_client_still_sending_after_the_close_is_read_out(self):
        ws, peer, gauge = self._connect()
        self.hub.call_soon(ws.close_now, CloseCode.GOING_AWAY)
        self.assertEqual(peer.frame()[0], Opcode.CLOSE)
        peer.send(Opcode.CLOSE, struct.pack("!H", CloseCode.GOING_AWAY))
        self.assertTrue(_wait_until(lambda: ws.lingering))
        for _ in range(50):
            peer.sock.sendall(b"sent before the client read the close" * 10)
        time.sleep(0.05)
        self.assertEqual(gauge.count, 1, "the socket stays open while it talks")
        peer.sock.close()
        self.assertTrue(_wait_until(lambda: gauge.count == 0))
        self.assertNotIn(ws.fd, self.hub.connections)

    def test_messages_are_served_in_order_one_job_at_a_time(self):
        _ws, peer, _gauge = self._connect()
        for i in range(5):
            peer.send(Opcode.TEXT, str(i).encode())
        self.assertTrue(_wait_until(lambda: len(self.served) == 5))
        self.assertEqual(self.served, ["0", "1", "2", "3", "4"])
        self.assertEqual(self.max_running, 1)

    def test_a_ping_behind_a_message_is_answered_after_it(self):
        self.release.clear()
        _ws, peer, _gauge = self._connect()
        peer.sock.sendall(
            _masked_client_frame(Opcode.TEXT, b"first")
            + _masked_client_frame(Opcode.PING, b"after")
        )
        time.sleep(0.1)
        self.assertEqual(self.served, [])
        self.release.set()
        self.assertEqual(peer.frame(), (Opcode.PONG, b"after"))
        self.assertEqual(self.served, ["first"])

    def test_a_full_lane_stops_reading_until_it_drains(self):
        self.release.clear()
        ws, peer, _gauge = self._connect()
        for i in range(Websocket.LANE_DEPTH + 4):
            peer.send(Opcode.TEXT, str(i).encode())
            time.sleep(0.01)
        self.assertTrue(_wait_until(lambda: not ws._reading))
        self.assertLessEqual(len(ws._lane), Websocket.LANE_DEPTH)
        self.release.set()
        self.assertTrue(
            _wait_until(lambda: len(self.served) == Websocket.LANE_DEPTH + 4)
        )
        self.assertEqual(self.served, [str(i) for i in range(Websocket.LANE_DEPTH + 4)])
        self.assertTrue(ws._reading)

    def test_a_full_lane_does_not_count_against_the_ping_answer(self):
        self.release.clear()
        with patch.object(TimeoutManager, "TIMEOUT", 0.3):
            ws, peer, _gauge = self._connect()
            for i in range(Websocket.LANE_DEPTH + 2):
                peer.send(Opcode.TEXT, str(i).encode())
                time.sleep(0.01)
            self.assertTrue(_wait_until(lambda: not ws._reading))
            self.hub.call_soon(ws._send_ping_frame)
            self.assertEqual(peer.frame()[0], Opcode.PING)
            peer.send(Opcode.PONG)
            time.sleep(0.6)
            self.assertIs(ws.state, ConnectionState.OPEN, "its pong sits unread")
            self.release.set()
            self.assertTrue(
                _wait_until(lambda: len(self.served) == Websocket.LANE_DEPTH + 2)
            )
            time.sleep(0.6)
            self.assertIs(ws.state, ConnectionState.OPEN)

    def test_a_round_asks_once_and_hands_idle_subscribers_one_frame(self):
        idle = [self._connect() for _ in range(5)]
        busy, busy_peer, _gauge = self._connect()
        for ws, _peer, _gauge in [*idle, (busy, busy_peer, None)]:
            ws._channels = frozenset({("db", "chan")})
            ws._session_validated_until = float("inf")
            ws._validated_session_sid = ws._session.sid
        one_by_one = []

        def dispatch_bus_notifications():
            busy._waiting_for_dispatch = False
            one_by_one.append(busy._poll_round)

        busy._dispatch_bus_notifications = dispatch_bus_notifications
        self.release.clear()
        busy_peer.send(Opcode.TEXT, b"busy")
        self.assertTrue(_wait_until(lambda: self.running == 1))
        notifications = [{"id": 7, "message": {"type": "t", "payload": 1}}]
        env = MagicMock()
        poll = env.__getitem__.return_value._poll_batch
        poll.return_value = (notifications, False)
        cursor = MagicMock()
        cursor.__enter__.return_value = MagicMock()
        with (
            patch("odoo.addons.bus.websocket.acquire_cursor", return_value=cursor),
            patch.object(Websocket, "new_env", return_value=env),
        ):
            poll_round = dispatch.open_poll_round()
            websocket_module._wake_websockets(
                [ws for ws, _peer, _gauge in idle] + [busy], poll_round
            )
            for _ws, peer, _gauge in idle:
                opcode, payload = peer.frame()
                self.assertEqual(opcode, Opcode.TEXT)
                self.assertEqual(json_loads(payload), notifications)
            self.assertEqual(poll.call_count, 1, "one question for the round")
            self.assertEqual(one_by_one, [], "the busy one waits for its job")
            self.release.set()
            self.assertTrue(_wait_until(lambda: one_by_one))
        self.assertEqual(one_by_one, [poll_round], "and then shares the round")
        for ws, _peer, _gauge in idle:
            self.assertEqual(ws._dispatch_state.ignore_ids, [7])

    def test_a_round_checks_its_due_sessions_on_its_cursor_and_closes_the_expired(self):
        trusted, due, expired = (self._connect() for _ in range(3))
        for index, (ws, _peer, _gauge) in enumerate((trusted, due, expired)):
            ws._channels = frozenset({("db", "chan")})
            ws._session = MagicMock(db="db", sid=f"sid{index}", uid=index + 1)
            ws._validated_session_sid = ws._session.sid
        trusted[0]._session_validated_until = float("inf")
        due[0]._session_validated_until = 0.0
        expired[0]._session_validated_until = 0.0
        notifications = [{"id": 9, "message": {"type": "t", "payload": 1}}]
        env = MagicMock()
        poll = env.__getitem__.return_value._poll_batch
        poll.return_value = (notifications, False)
        cursor = MagicMock()
        cursor.__enter__.return_value = MagicMock()
        checked = []

        expired_session = expired[0]._session

        def is_session_valid(session, _env, fresh_primary_cr=None):
            checked.append((session.sid, fresh_primary_cr))
            return session is not expired_session

        with (
            patch(
                "odoo.addons.bus.websocket.acquire_cursor", return_value=cursor
            ) as acquire,
            patch.object(Websocket, "new_env", return_value=env),
            patch(
                "odoo.addons.bus.websocket._follow_session_chain",
                side_effect=lambda session: session,
            ),
            patch(
                "odoo.addons.bus.websocket.is_session_valid",
                side_effect=is_session_valid,
            ),
        ):
            poll_round = dispatch.open_poll_round()
            websocket_module._wake_websockets(
                [trusted[0], due[0], expired[0]], poll_round
            )
            for _ws, peer, _gauge in (trusted, due):
                opcode, payload = peer.frame()
                self.assertEqual(opcode, Opcode.TEXT)
                self.assertEqual(json_loads(payload), notifications)
            opcode, payload = expired[1].frame()
        self.assertEqual(opcode, Opcode.CLOSE)
        self.assertEqual(struct.unpack("!H", payload[:2])[0], CloseCode.SESSION_EXPIRED)
        self.assertEqual(
            sorted(sid for sid, _cr in checked),
            ["sid1", "sid2"],
            "only the due sessions are checked, each once",
        )
        self.assertEqual(
            {id(cr) for _sid, cr in checked},
            {id(cursor.__enter__.return_value)},
            "on the round's cursor",
        )
        self.assertEqual(acquire.call_count, 1, "one cursor for the round")
        self.assertEqual(poll.call_count, 1, "one question for the round")
        self.assertGreater(due[0]._session_validated_until, 0.0)
        self.assertEqual(expired[0]._dispatch_state.ignore_ids, [])

    def test_a_session_gone_from_the_store_closes_alone_in_its_round(self):
        kept, gone = self._connect(), self._connect()
        for index, (ws, _peer, _gauge) in enumerate((kept, gone)):
            ws._channels = frozenset({("db", "chan")})
            ws._session = MagicMock(db="db", sid=f"sid{index}", uid=index + 1)
            ws._validated_session_sid = ws._session.sid
            ws._session_validated_until = 0.0
        notifications = [{"id": 11, "message": {"type": "t", "payload": 1}}]
        env = MagicMock()
        poll = env.__getitem__.return_value._poll_batch
        poll.return_value = (notifications, False)
        cursor = MagicMock()
        cursor.__enter__.return_value = MagicMock()
        gone_sid = gone[0]._session.sid

        def follow_session_chain(session):
            if session.sid == gone_sid:
                raise SessionExpiredException
            return session

        with (
            patch(
                "odoo.addons.bus.websocket.acquire_cursor", return_value=cursor
            ) as acquire,
            patch.object(Websocket, "new_env", return_value=env),
            patch(
                "odoo.addons.bus.websocket._follow_session_chain",
                side_effect=follow_session_chain,
            ),
            patch("odoo.addons.bus.websocket.is_session_valid", return_value=True),
            self.assertNoLogs("odoo.addons.bus.websocket", "WARNING"),
        ):
            websocket_module._wake_websockets(
                [kept[0], gone[0]], dispatch.open_poll_round()
            )
            opcode, payload = kept[1].frame()
            self.assertEqual(opcode, Opcode.TEXT)
            self.assertEqual(json_loads(payload), notifications)
            opcode, payload = gone[1].frame()
        self.assertEqual(opcode, Opcode.CLOSE)
        self.assertEqual(struct.unpack("!H", payload[:2])[0], CloseCode.SESSION_EXPIRED)
        self.assertEqual(acquire.call_count, 1, "the round kept its one cursor")
        self.assertEqual(poll.call_count, 1)

    def test_a_connection_keeps_a_view_of_its_session_not_the_session(self):
        ws, _peer, _gauge = self._connect()
        self.assertIsInstance(ws._session, websocket_module.SessionView)
        self.assertFalse(hasattr(ws._session, "__dict__"))
        live = MagicMock(sid="sid1", uid=7, db="db", context={"lang": "en_US"})
        with patch(
            "odoo.addons.bus.websocket._follow_session_chain", return_value=live
        ):
            request = websocket_module.WebsocketRequest("db", MagicMock(), ws)
            self.assertIs(request._acquire_session(), live, "a message gets it whole")
        self.assertIsInstance(ws._session, websocket_module.SessionView)
        self.assertEqual((ws._session.sid, ws._session.uid), ("sid1", 7))
        self.assertEqual(ws._session.context, {"lang": "en_US"})

    def test_a_connection_keeps_its_handshake_facts_not_the_request(self):
        httprequest = MagicMock(remote_addr="203.0.113.7", cookies={"tz": "UTC"})
        httprequest.user_agent.string = "Mozilla/5.0 (X11; Linux x86_64)"
        httprequest.user_agent.platform = "linux"
        httprequest.user_agent.browser = "firefox"
        ws, _peer, _gauge = self._connect(httprequest=httprequest)
        facts = ws._handshake
        self.assertIsInstance(facts, websocket_module.HandshakeFacts)
        self.assertFalse(hasattr(facts, "__dict__"))
        request = websocket_module.WebsocketRequest("db", facts, ws)
        self.assertEqual(request.httprequest.remote_addr, "203.0.113.7")
        self.assertEqual(
            (facts.user_agent.platform, facts.user_agent.browser), ("linux", "firefox")
        )
        with self.assertRaises(AttributeError):
            facts.headers

    def test_dispatch_requests_coalesce_behind_a_running_job(self):
        self.release.clear()
        ws, peer, _gauge = self._connect()
        dispatched = []
        ws._dispatch_bus_notifications = lambda: (
            dispatched.append(ws._waiting_for_dispatch)
            or setattr(ws, "_waiting_for_dispatch", False)
        )
        peer.send(Opcode.TEXT, b"busy")
        self.assertTrue(_wait_until(lambda: self.running == 1))
        for _ in range(5):
            ws.trigger_notification_dispatching()
        self.release.set()
        self.assertTrue(_wait_until(lambda: len(dispatched) == 1))
        time.sleep(0.05)
        self.assertEqual(len(dispatched), 1)

    def test_a_peer_that_reads_nothing_is_cut_off(self):
        ws, peer, gauge = self._connect()
        peer.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        ws.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        with patch.object(Websocket, "WRITE_STALL_TIMEOUT", 0.3):
            self.hub.call_soon(ws._write_data_frame, b"x" * (1 << 20), MagicMock())
            self.assertTrue(_wait_until(lambda: ws._outbuf))
            self.assertTrue(
                _wait_until(lambda: ws.state is ConnectionState.CLOSED, timeout=5)
            )
        self.assertTrue(_wait_until(lambda: gauge.count == 0))
        self.assertNotIn(ws.fd, self.hub.connections)
        self.assertEqual(self.hub.outbound, 0)
        self.assertEqual(self.hub.write_stalls, 1)

    def test_idle_connections_are_pinged_with_jitter(self):
        with (
            patch.object(TimeoutManager, "INACTIVITY_TIMEOUT", 0.2),
            patch.object(TimeoutManager, "TIMEOUT", 5),
        ):
            pairs = [self._connect() for _ in range(5)]
            for _ws, peer, _gauge in pairs:
                self.assertEqual(peer.frame()[0], Opcode.PING)
        manager = TimeoutManager()
        intervals = {manager._inactivity_timeout() for _ in range(50)}
        self.assertGreater(len(intervals), 1)
        low = TimeoutManager.INACTIVITY_TIMEOUT * (1 - TimeoutManager.PING_JITTER)
        high = TimeoutManager.INACTIVITY_TIMEOUT * (1 + TimeoutManager.PING_JITTER)
        self.assertTrue(all(low <= i <= high for i in intervals))

    def test_close_all_reaches_every_open_connection(self):
        pairs = [self._connect() for _ in range(3)]
        self.assertTrue(self.hub.close_all(CloseCode.GOING_AWAY))
        for _ws, peer, _gauge in pairs:
            opcode, payload = peer.frame()
            self.assertEqual(opcode, Opcode.CLOSE)
            self.assertEqual(struct.unpack("!H", payload[:2])[0], CloseCode.GOING_AWAY)

    def _dispatch_counter(self, ws):
        dispatched = []

        def dispatch_bus_notifications():
            ws._waiting_for_dispatch = False
            dispatched.append(time.monotonic())

        ws._dispatch_bus_notifications = dispatch_bus_notifications
        return dispatched

    def _choke(self, ws, peer, size):
        peer.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        ws.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        self.hub.call_soon(ws._write_data_frame, b"x" * size, MagicMock())
        self.assertTrue(_wait_until(lambda: len(ws._outbuf) > size // 2))

    def test_a_slow_reader_holds_back_only_its_own_dispatches(self):
        slow, slow_peer, slow_gauge = self._connect()
        fast, _fast_peer, _gauge = self._connect()
        slow_dispatches = self._dispatch_counter(slow)
        fast_dispatches = self._dispatch_counter(fast)
        with patch.object(Websocket, "WRITE_STALL_TIMEOUT", 1.0):
            self._choke(slow, slow_peer, 4 * Websocket.WRITE_BUFFER_LIMIT)
            slow.trigger_notification_dispatching()
            fast.trigger_notification_dispatching()
            self.assertTrue(_wait_until(lambda: fast_dispatches))
            time.sleep(0.1)
            self.assertEqual(
                slow_dispatches, [], "no dispatch while its buffer is full"
            )
            self.assertTrue(
                _wait_until(lambda: slow.state is ConnectionState.CLOSED, timeout=5)
            )
        self.assertIs(fast.state, ConnectionState.OPEN)
        # CLOSED is set a few statements before the loop releases the slot
        self.assertTrue(_wait_until(lambda: slow_gauge.count == 0))
        self.assertEqual(self.hub.write_stalls, 1)

    def test_the_process_outbound_budget_holds_every_dispatch(self):
        slow, slow_peer, _gauge = self._connect()
        fast, _fast_peer, _gauge = self._connect()
        fast_dispatches = self._dispatch_counter(fast)
        with patch.object(WebsocketHub, "OUTBOUND_LIMIT", 64 * 1024):
            self._choke(slow, slow_peer, 1024 * 1024)
            fast.trigger_notification_dispatching()
            time.sleep(0.2)
            self.assertEqual(
                fast_dispatches, [], "held while the process is over budget"
            )
            self.assertIn(fast, self.hub.deferred)
            slow_peer.sock.setblocking(False)
            deadline = time.monotonic() + 5
            while not fast_dispatches and time.monotonic() < deadline:
                try:
                    slow_peer.sock.recv(1 << 20)
                except BlockingIOError:
                    time.sleep(0.005)
            self.assertTrue(fast_dispatches, "resumed once the budget drained")

    def test_the_loop_reports_its_lag_and_dispatch_latency(self):
        ws, _peer, _gauge = self._connect()
        self._dispatch_counter(ws)
        ws.trigger_notification_dispatching()
        self.assertTrue(_wait_until(lambda: self.hub.dispatch_latency.count == 1))
        self.assertTrue(_wait_until(lambda: self.hub.loop_lag.count >= 1, timeout=3))
        self.assertGreaterEqual(self.hub.dispatch_latency.recent_max, 0.0)


@tagged("-at_install", "post_install")
class TestDbExecutor(BaseCase):
    def test_never_runs_more_threads_than_its_size(self):
        executor = DbExecutor(2)
        self.addCleanup(executor.close)
        gate = threading.Event()
        running = []
        peak = []

        def job():
            running.append(1)
            peak.append(len(running))
            gate.wait(5)
            running.pop()

        for _ in range(10):
            executor.submit(job)
        self.assertTrue(_wait_until(lambda: executor.busy == 2))
        self.assertEqual(executor.queued, 8)
        gate.set()
        self.assertTrue(executor.wait_idle(time.monotonic() + 5))
        self.assertEqual(max(peak), 2)

    def test_a_closed_executor_refuses_jobs(self):
        executor = DbExecutor(1)
        executor.close()
        self.assertFalse(executor.submit(lambda: None))


@tagged("-at_install", "post_install")
class TestWebsocketHubOverHttp(WebsocketCase):
    def _shared_session_cookie(self):
        # authenticate() deletes the session it replaces: one session for all.
        return f"session_id={self.authenticate(None, None).sid}"

    def test_a_broadcast_reaches_two_hundred_subscribers(self):
        last = self.env["bus.bus"]._bus_last_id()
        cookie = self._shared_session_cookie()
        websockets = [self.websocket_connect(cookie=cookie) for _ in range(200)]
        for websocket in websockets:
            self.subscribe(websocket, [self.channel("hub_broadcast")], last)
        self.env["bus.bus"]._sendone(self.target("hub_broadcast"), "hub_type", "hello")
        self.trigger_notification_dispatching([self.target("hub_broadcast")])
        for websocket in websockets:
            notifications = json_loads(websocket.recv())
            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0]["message"]["payload"], "hello")

    def test_five_hundred_websockets_hold_no_thread_each(self):
        before = threading.active_count()
        cookie = self._shared_session_cookie()
        websockets = [
            self.websocket_connect(cookie=cookie, ping_after_connect=False)
            for _ in range(500)
        ]
        for websocket in websockets:
            websocket.ping()
            websocket.recv_data_frame(control_frame=True)
        self.assertEqual(len(websocket_module._open_websockets()), 500)
        self.assertLess(threading.active_count() - before, 64)


@tagged("-at_install", "post_install")
class TestDrainOnStop(WebsocketCase):
    def test_a_stop_asks_every_websocket_to_reconnect_and_skips_close_hooks(self):
        hub = WebsocketHub(db_threads=lambda: 2)
        self.startPatcher(patch.object(websocket_module, "_hub", hub))
        self.startPatcher(
            patch.dict(os.environ, {"ODOO_WEBSOCKET_DRAIN_TIMEOUT": "1.5"})
        )
        cookie = f"session_id={self.authenticate(None, None).sid}"
        websockets = [self.websocket_connect(cookie=cookie) for _ in range(50)]
        self.assertEqual(len(hub.connections), 50)
        silent = websockets.pop()
        drained = threading.Event()
        elapsed = []

        def drain():
            started = time.monotonic()
            websocket_module._drain_on_stop()
            elapsed.append(time.monotonic() - started)
            drained.set()

        with patch(
            "odoo.addons.bus.models.ir_websocket.IrWebsocket._on_websocket_closed"
        ) as close_hook:
            threading.Thread(target=drain, daemon=True).start()
            for websocket in websockets:
                self.assert_close_with_code(websocket, CloseCode.GOING_AWAY)
            self.assertTrue(drained.wait(5))
            self.wait_remaining_websocket_connections()
        self.assert_close_with_code(silent, CloseCode.GOING_AWAY)
        close_hook.assert_not_called()
        self.assertEqual(hub.connections, {})
        self.assertGreaterEqual(elapsed[0], 1.5, "the silent client is waited for")
        self.assertLess(elapsed[0], 3.0, "then cut at the drain timeout")
        with self.assertRaises(WebSocketBadStatusException) as refused:
            self.websocket_connect()
        self.assertEqual(refused.exception.status_code, 503)


@tagged("-at_install", "post_install")
class TestWebsocketMetricsAndLimits(BaseCase):
    def test_the_loop_metrics_are_exported(self):
        exposition = render_prometheus_exposition()
        for family in (
            "odoo_websocket_db_threads",
            "odoo_websocket_db_queue",
            "odoo_websocket_outbound_bytes",
            "odoo_websocket_write_stalls_total",
            "odoo_websocket_dispatch_latency_seconds_max",
            "odoo_websocket_loop_lag_seconds_max",
        ):
            self.assertIn(f"# TYPE {family} ", exposition)

    def test_an_overrunning_job_has_its_queries_cancelled_and_nothing_more(self):
        server = WebsocketServer.__new__(WebsocketServer)
        server.logger = MagicMock()
        server._cancelled_overruns = {}
        server._overruns_cancelled = 0
        release = threading.Event()
        job = threading.Thread(target=release.wait, args=(5,), daemon=True)
        job.type = "websocket_job"
        job.start_time = time.monotonic() - 10_000
        job.start()
        self.addCleanup(release.set)
        with (
            patch(
                "odoo.service._threaded._cancel_thread_queries", return_value=1
            ) as cancel,
            patch.object(
                type(server), "settings", new_callable=PropertyMock
            ) as settings,
        ):
            settings.return_value.get_real_time_budget.return_value = 120
            server.cancel_overrunning_jobs()
            server.cancel_overrunning_jobs()
        cancel.assert_called_once()
        self.assertIs(cancel.call_args.args[0], job)
        self.assertEqual(server._overruns_cancelled, 1)
