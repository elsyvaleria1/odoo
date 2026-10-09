import contextlib
import gc
import inspect
import struct
import time
import unittest
from queue import Empty, SimpleQueue
from threading import Event
from unittest.mock import patch

from werkzeug.exceptions import BadRequest

from odoo.libs.json import dumps as json_dumps

try:
    import websocket
except ImportError:
    websocket = None

from odoo.http import request
from odoo.tests import HttpCase
from odoo.tests.common import (
    HOST,
    TEST_CURSOR_COOKIE_NAME,
    Like,
    _registry_test_lock,
    release_test_lock,
)

from ..models.bus import channel_with_db, dispatch, hashable
from ..tools.channel_capability import (
    channel_capability,
    channel_target,
    register_channel_scope,
)
from ..websocket import CloseCode, Websocket, WebsocketConnectionHandler

TEST_CHANNEL = register_channel_scope(
    "bus_test",
    purpose="tests of the bus: a channel a test names",
    lifetime="undated: test channels",
)


def channel_key(env, channel):
    return hashable(channel_with_db(env.cr.dbname, channel))


def channel_keys(env, channels):
    return [channel_key(env, channel) for channel in channels]


class WebsocketCase(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if websocket is None:
            cls._logger.warning("websocket-client module is not installed")
            raise unittest.SkipTest("websocket-client module is not installed")
        cls._BASE_WEBSOCKET_URL = f"ws://{HOST}:{cls.http_port()}/websocket"
        cls._WEBSOCKET_URL = (
            f"{cls._BASE_WEBSOCKET_URL}?version={WebsocketConnectionHandler._VERSION}"
        )
        websocket_allowed_patch = patch.object(
            WebsocketConnectionHandler, "websocket_allowed", return_value=True
        )
        cls.startClassPatcher(websocket_allowed_patch)

    def setUp(self):
        super().setUp()
        self._websockets = set()
        self._websocket_close_events = []
        self._pending_websocket_close_events = SimpleQueue()
        original_open_connection = WebsocketConnectionHandler.open_connection

        def _mocked_open_connection(*args, **kwargs):
            response = original_open_connection(*args, **kwargs)
            websocket_closed_event = Event()
            self._websocket_close_events.append(websocket_closed_event)
            self._pending_websocket_close_events.put(websocket_closed_event)
            return response

        self.startPatcher(
            patch.object(
                WebsocketConnectionHandler, "open_connection", _mocked_open_connection
            )
        )
        original_adopt = Websocket._adopt
        original_teardown = Websocket._teardown

        def _mocked_adopt(websocket, *args):
            try:
                websocket._test_closed_event = (
                    self._pending_websocket_close_events.get_nowait()
                )
            except Empty:
                websocket._test_closed_event = None
            original_adopt(websocket, *args)

        def _mocked_teardown(websocket):
            try:
                original_teardown(websocket)
            finally:
                event = getattr(websocket, "_test_closed_event", None)
                if event is not None:
                    event.set()

        self.startPatcher(patch.object(Websocket, "_adopt", _mocked_adopt))
        self.startPatcher(patch.object(Websocket, "_teardown", _mocked_teardown))
        self.enterContext(release_test_lock())
        self.http_request_key = "websocket"

    def tearDown(self):
        self._close_websockets()
        super().tearDown()

    def _close_websockets(self):
        for ws in self._websockets:
            if ws.connected:
                ws.close(CloseCode.CLEAN)
        self.wait_remaining_websocket_connections()

    @contextlib.contextmanager
    def allow_requests(self, *args, **kwargs):
        with _registry_test_lock, super().allow_requests(*args, **kwargs):
            yield

    def assertCanOpenTestCursor(self):
        allowed_methods = [
            ("acquire_cursor", Like(".../bus/websocket.py")),
        ]
        if (
            any(
                frame.function == function and frame.filename == filename
                for frame in inspect.stack()
                for function, filename in allowed_methods
            )
            or request
        ):
            return super().assertCanOpenTestCursor()
        raise BadRequest("Opening a cursor from an unknown method in websocket test.")

    def channel(self, name):
        """The capability a test's client subscribes to ``name`` with."""
        return channel_capability(self.env, TEST_CHANNEL, name)

    def target(self, name):
        """The channel a test's server sends ``name`` to."""
        return channel_target(self.env, TEST_CHANNEL, name)

    def websocket_connect(self, *args, ping_after_connect=True, **kwargs):
        if "cookie" not in kwargs:
            self.session = self.authenticate(None, None)
            kwargs["cookie"] = f"session_id={self.session.sid}"
        kwargs.setdefault("timeout", 10)
        kwargs["cookie"] += f";{TEST_CURSOR_COOKIE_NAME}={self.http_request_key}"
        ws = websocket.create_connection(self._WEBSOCKET_URL, *args, **kwargs)
        if ping_after_connect:
            ws.ping()
            ws.recv_data_frame(control_frame=True)
        self._websockets.add(ws)
        return ws

    def subscribe(self, websocket, channels=None, last=None, wait_for_dispatch=True):
        dispatch_bus_notification_done = Event()
        original_dispatch_bus_notifications = Websocket._dispatch_bus_notifications

        def _mocked_dispatch_bus_notifications(self, *args):
            original_dispatch_bus_notifications(self, *args)
            dispatch_bus_notification_done.set()

        with patch.object(
            Websocket, "_dispatch_bus_notifications", _mocked_dispatch_bus_notifications
        ):
            sub = {
                "event_name": "subscribe",
                "data": {
                    "channels": channels or [],
                },
            }
            if last is not None:
                sub["data"]["last"] = last
            websocket.send(json_dumps(sub))
            if wait_for_dispatch:
                self.assertTrue(
                    dispatch_bus_notification_done.wait(timeout=5),
                    "Subscription should have triggered a notification dispatch "
                    "(use wait_for_dispatch=False for subscriptions expected to "
                    "be rejected)",
                )

    def trigger_notification_dispatching(self, channels):
        self.env.cr.precommit.run()
        channels = [
            hashable(channel_with_db(self.registry.db_name, c)) for c in channels
        ]
        websockets = set()
        for channel in channels:
            websockets.update(dispatch._channels_to_ws.get(hashable(channel), []))
        for websocket in websockets:
            websocket.trigger_notification_dispatching()

    def wait_remaining_websocket_connections(self):
        for event in self._websocket_close_events:
            self.assertTrue(
                event.wait(5),
                "A websocket connection did not terminate within 5 seconds",
            )

    def assert_released(self, refs, timeout=10.0):
        # The job thread that ran a connection's last job lets go of it a
        # moment after the job returned, which is when the test is woken.
        # No strong reference survives an iteration: a connection seen alive
        # once, kept in a list across the next gc.collect(), is one its cycle
        # (connection, frame parser, bound method) can never be freed from.
        deadline = time.monotonic() + timeout
        while True:
            gc.collect()
            if all(ref() is None for ref in refs) or time.monotonic() > deadline:
                break
            time.sleep(0.02)
        self.assertEqual([ref() for ref in refs], [None] * len(refs))

    def assert_close_with_code(self, websocket, expected_code, expected_reason=None):
        opcode, payload = websocket.recv_data()
        self.assertEqual(opcode, 8)
        code = struct.unpack("!H", payload[:2])[0]
        self.assertEqual(code, expected_code)
        if expected_reason:
            self.assertEqual(payload[2:].decode(), expected_reason)


class BusCase:
    def _reset_bus(self):
        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()
