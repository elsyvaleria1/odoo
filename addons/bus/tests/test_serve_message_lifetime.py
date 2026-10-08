import gc
import weakref
from unittest.mock import MagicMock, patch

from odoo.tests import BaseCase, tagged

from .. import websocket as websocket_module
from ..websocket import Websocket


def _bare_websocket():
    return Websocket(MagicMock(), MagicMock(db="db"), {}, httprequest=MagicMock())


@tagged("-at_install", "post_install")
class TestServeMessageLifetime(BaseCase):
    def _reachable_between_messages(self):
        built = []
        observed = []

        class _Request:
            def __init__(self, db, httprequest, ws):
                self.registry = object()

            def __enter__(self):
                built.append(weakref.ref(self))
                return self

            def __exit__(self, *args):
                return False

            def serve_websocket_message(self, message):
                pass

        ws = _bare_websocket()
        with patch.object(websocket_module, "WebsocketRequest", _Request):
            ws._message_job(b"ping")
            gc.collect()
            observed.append(built[0]() is not None)
        self.assertEqual(len(built), 1, "exactly one request should be built")
        self.assertEqual(
            len(observed), 1, "the lane should have served the message once"
        )
        return observed[0]

    def test_request_is_released_between_messages(self):
        self.assertFalse(
            self._reachable_between_messages(),
            "the served request is still reachable once its job returned: it is "
            "pinning its registry and environment for as long as the socket "
            "stays open. Serve each message from its own frame "
            "(WebsocketConnectionHandler._serve_message) instead of binding it "
            "in the lane job.",
        )

    def test_sentinel_messages_build_no_request(self):
        built = []

        class _Request:
            def __init__(self, db, httprequest, ws):
                built.append(message_seen[0])

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def serve_websocket_message(self, message):
                pass

        message_seen = [None]
        ws = _bare_websocket()
        with patch.object(websocket_module, "WebsocketRequest", _Request):
            for msg in (b"\x00", b"ping"):
                message_seen[0] = msg
                ws._deliver([msg])
                while ws._lane:
                    ws._message_job(ws._lane.popleft())
        self.assertEqual(built, [b"ping"], "only the non-sentinel message is served")
