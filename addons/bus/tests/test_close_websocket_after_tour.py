import gc
import weakref
from unittest.mock import patch

from odoo.tests import tagged

from .. import websocket as websocket_module
from .common import WebsocketCase


@tagged("-at_install", "post_install")
class TestCloseWebsocketAfterTour(WebsocketCase):
    @patch("odoo.tests.common.ChromeBrowser")
    def test_ensure_websocket_closed_after_tour(self, mocked_brower_class):
        served = []

        def navigate_to_side_effect(*args, **kwargs):
            self.websocket_connect()
            open_websockets = websocket_module._open_websockets()
            self.assertEqual(len(open_websockets), 1)
            served.extend(weakref.ref(ws) for ws in open_websockets)

        mocked_brower_class.return_value.navigate_to.side_effect = (
            navigate_to_side_effect
        )

        self.browser_js("/odoo", "")
        self.assertTrue(served)
        self.assertEqual(len(websocket_module._open_websockets()), 0)
        self.wait_remaining_websocket_connections()
        gc.collect()
        self.assertEqual([ref() for ref in served], [None])
