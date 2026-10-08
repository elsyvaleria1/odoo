import socket
import struct
import threading
import time
from unittest.mock import MagicMock, patch

from odoo.libs.json import loads as json_loads
from odoo.tests import BaseCase, tagged

from .. import websocket as websocket_module
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
        self.assertTrue(_wait_until(lambda: ws.fd not in self.hub.connections))
        self.assertIs(ws.state, ConnectionState.CLOSED)
        self.assertTrue(self.torn_down.wait(5), "the close hooks run after the close")
        self.assertEqual(gauge.count, 0)

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
        self.assertTrue(_wait_until(lambda: ws.fd not in self.hub.connections))
        self.assertEqual(self.hub.outbound, 0)
        self.assertEqual(self.hub.write_stalls, 1)
        self.assertEqual(gauge.count, 0)

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
            self.subscribe(websocket, ["hub_broadcast"], last)
        self.env["bus.bus"]._sendone("hub_broadcast", "hub_type", "hello")
        self.trigger_notification_dispatching(["hub_broadcast"])
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
