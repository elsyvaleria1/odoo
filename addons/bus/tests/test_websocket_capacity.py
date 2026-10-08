import os
import time
from unittest.mock import patch

try:
    from websocket import WebSocketBadStatusException
except ImportError:
    WebSocketBadStatusException = None

from odoo.service import lifecycle
from odoo.service.metrics import render_prometheus_exposition
from odoo.tests import BaseCase, tagged

from .. import websocket as websocket_module
from ..websocket import CloseCode, ConnectionGauge
from .common import WebsocketCase


class _ManualClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


@tagged("-at_install", "post_install")
class TestConnectionGauge(BaseCase):
    def test_reserves_up_to_the_limit_then_refuses(self):
        gauge = ConnectionGauge(2)
        self.assertTrue(gauge.reserve())
        self.assertTrue(gauge.reserve())
        with self.assertLogs("odoo.addons.bus.websocket", "WARNING"):
            self.assertFalse(gauge.reserve())
        self.assertEqual(gauge.count, 2)
        self.assertEqual(gauge.refused, 1)
        gauge.release()
        self.assertTrue(gauge.reserve())

    def test_zero_is_unbounded(self):
        gauge = ConnectionGauge(0)
        for _ in range(100):
            self.assertTrue(gauge.reserve())
        self.assertEqual(gauge.count, 100)

    def test_refusals_are_logged_once_per_interval(self):
        clock = _ManualClock(100.0)
        gauge = ConnectionGauge(1, clock=clock)
        gauge.reserve()
        with self.assertLogs("odoo.addons.bus.websocket", "WARNING") as logs:
            for _ in range(5):
                gauge.reserve()
            clock.now += ConnectionGauge.REFUSAL_LOG_INTERVAL
            gauge.reserve()
        self.assertEqual(len(logs.output), 2)
        self.assertIn("Refused 1 websocket", logs.output[0])
        self.assertIn("Refused 5 websocket", logs.output[1])
        self.assertEqual(gauge.refused, 6)

    def test_the_cap_reads_its_environment_variable(self):
        with patch.dict(os.environ, {"ODOO_WEBSOCKET_MAX_CONNECTIONS": "7"}):
            self.assertEqual(ConnectionGauge().limit, 7)

    def test_the_descriptor_budget_counts_every_websocket_under_the_cap(self):
        with patch.dict(os.environ, {"ODOO_WEBSOCKET_MAX_CONNECTIONS": "0"}):
            without = lifecycle._get_descriptor_budget_demand()
        with patch.dict(os.environ, {"ODOO_WEBSOCKET_MAX_CONNECTIONS": "100"}):
            with_cap = lifecycle._get_descriptor_budget_demand()
        self.assertGreaterEqual(with_cap - without, 100)


@tagged("-at_install", "post_install")
class TestWebsocketCapacity(WebsocketCase):
    def _wait_for_count(self, gauge, count):
        deadline = time.monotonic() + 5
        while gauge.count != count and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(gauge.count, count)

    def test_handshake_over_the_cap_is_answered_503(self):
        gauge = ConnectionGauge(1)
        self.startPatcher(patch.object(websocket_module, "_connection_gauge", gauge))
        first = self.websocket_connect()
        self.assertEqual(gauge.count, 1)
        with (
            self.assertLogs("odoo.addons.bus.websocket", "WARNING"),
            self.assertRaises(WebSocketBadStatusException) as refused,
        ):
            self.websocket_connect()
        self.assertEqual(refused.exception.status_code, 503)
        self.assertEqual(refused.exception.resp_headers.get("retry-after"), "5")
        self.assertEqual(gauge.count, 1)
        first.close(CloseCode.CLEAN)
        self.wait_remaining_websocket_connections()
        self._wait_for_count(gauge, 0)
        self.websocket_connect()
        self.assertEqual(gauge.count, 1)

    def test_the_gauge_is_exported_as_a_metric(self):
        gauge = ConnectionGauge(3)
        self.startPatcher(patch.object(websocket_module, "_connection_gauge", gauge))
        self.websocket_connect()
        exposition = render_prometheus_exposition()
        pid = os.getpid()
        self.assertIn(f'odoo_websocket_connections{{pid="{pid}"}} 1', exposition)
        self.assertIn(f'odoo_websocket_connections_max{{pid="{pid}"}} 3', exposition)
