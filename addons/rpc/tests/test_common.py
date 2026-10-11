import logging
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.rpc.controllers import common


class _FakeUserAgent:
    def __init__(self, string):
        self.string = string


class _FakeHttpRequest:
    def __init__(self, remote_addr, user_agent):
        self.remote_addr = remote_addr
        self.user_agent = _FakeUserAgent(user_agent)


class _FakeRequest:
    def __init__(self, remote_addr, user_agent="test-agent"):
        self.httprequest = _FakeHttpRequest(remote_addr, user_agent)


@tagged("post_install", "-at_install")
class TestWarnEndpointIsDeprecated(TransactionCase):

    def setUp(self):
        super().setUp()
        original_clients = common._WARNED_CLIENTS
        original_limit = common._WARNED_CLIENTS_LIMIT
        common._WARNED_CLIENTS = common.OrderedDict()
        common._WARNED_CLIENTS_LIMIT = 3
        self.addCleanup(setattr, common, "_WARNED_CLIENTS", original_clients)
        self.addCleanup(setattr, common, "_WARNED_CLIENTS_LIMIT", original_limit)
        self.logger = logging.getLogger("odoo.addons.rpc.tests.test_common")

    def _warn(self, client):
        with patch.object(common, "request", _FakeRequest(client)):
            common.warn_endpoint_is_deprecated(self.logger, "test.module")

    def test_new_clients_keep_warning_past_the_cap(self):
        for i in range(3):
            self._warn(f"10.0.0.{i}")
        self.assertEqual(len(common._WARNED_CLIENTS), 3)

        with self.assertLogs(self.logger, level="WARNING") as capture:
            self._warn("10.0.0.99")
        self.assertIn("10.0.0.99", capture.output[0])
        self.assertEqual(len(common._WARNED_CLIENTS), 3)

    def test_already_warned_client_is_not_warned_twice(self):
        self._warn("10.0.0.1")
        with self.assertRaises(AssertionError):
            with self.assertLogs(self.logger, level="WARNING"):
                self._warn("10.0.0.1")
