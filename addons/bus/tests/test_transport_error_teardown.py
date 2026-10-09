import time
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from odoo.tests import BaseCase, tagged

from ..websocket import (
    ConnectionState,
    ProtocolError,
    Websocket,
)


@tagged("-at_install", "post_install")
class TestTransportErrorTeardown(BaseCase):
    def _make_ws(self):
        sock = MagicMock()
        sock.recv.return_value = b""
        sock.send.side_effect = BrokenPipeError("peer gone")
        ws = Websocket(sock, MagicMock(db="somedb"), {})
        ws._clock = time.monotonic
        ws._timeout_manager = MagicMock()
        return ws

    def test_registry_load_failure_during_server_error_does_not_escape(self):
        ws = self._make_ws()
        ws.sock.send = MagicMock(side_effect=len)
        with (
            patch(
                "odoo.addons.bus.websocket.Registry",
                side_effect=Exception("database gone"),
            ),
            self.assertLogs("odoo.addons.bus.websocket", level="ERROR"),
        ):
            ws._handle_transport_error(RuntimeError("boom"))
        ws.sock.send.assert_called_once()
        self.assertEqual(ws.state, ConnectionState.CLOSING)

    def test_registry_reload_suppresses_error_log(self):
        ws = self._make_ws()
        ws.sock.send = MagicMock(side_effect=len)
        registry_before = MagicMock(registry_sequence=1)
        registry_before.check_signaling.return_value = MagicMock(registry_sequence=2)
        with (
            patch("odoo.addons.bus.websocket.Registry", return_value=registry_before),
            self.assertLogs("odoo.addons.bus.websocket", level="WARNING") as capture,
        ):
            ws._handle_transport_error(RuntimeError("boom"))
        self.assertTrue(
            any("registry has been reloaded" in line for line in capture.output)
        )
        self.assertFalse(any("ERROR" in line for line in capture.output))
        self.assertEqual(ws.state, ConnectionState.CLOSING)

    def test_send_close_frame_failure_falls_back_to_terminate(self):
        ws = self._make_ws()

        @contextmanager
        def fake_acquire_cursor(db):
            yield MagicMock()

        with (
            patch("odoo.addons.bus.websocket.acquire_cursor", fake_acquire_cursor),
            patch.object(Websocket, "new_env", return_value=MagicMock()),
            patch("odoo.addons.bus.websocket.dispatch") as dispatch_mock,
        ):
            ws._handle_transport_error(ProtocolError("bad frame"))
        ws.sock.send.assert_called_once()
        dispatch_mock.unsubscribe.assert_called_once_with(ws)
        ws.sock.close.assert_called_once()
        self.assertEqual(ws.state, ConnectionState.CLOSED)
