from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


class TestWebsocketJoinsTheProtocolContract(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create({"name": "WebSocket Config"})

    def _make_device(self, **overrides):
        vals = {
            "name": "WebSocket Device",
            "identifier": "WS-DEFAULT",
            "config_id": self.config.id,
            "comm_protocol": "websocket",
            "endpoint": "ws.example.com",
        }
        vals.update(overrides)
        return self.env["device.device"].create(vals)

    def test_the_module_contributes_its_protocol_value(self):
        selection = dict(
            self.env["device.device"]
            ._fields["comm_protocol"]
            .get_description(self.env)["selection"]
        )
        self.assertIn("websocket", selection)

    def test_websocket_is_persistent_streamed_not_polled(self):
        device_model = self.env["device.device"]
        self.assertIn("websocket", device_model._persistent_protocols())
        self.assertIn("websocket", device_model._streamed_protocols())
        self.assertNotIn("websocket", device_model._polled_protocols())

    def test_display_endpoint_and_default_port(self):
        device = self._make_device(identifier="WS-DISP")
        self.assertEqual(device.display_endpoint, "ws://ws.example.com:80")
        self.assertEqual(device._protocol_default_port(), 80)

    def test_the_reconnect_cron_leaves_a_persistent_protocol_alone(self):
        device = self._make_device(identifier="WS-DISC")
        device.write(
            {
                "connection_state": "disconnected",
                "date_last_data_received": fields.Datetime.now()
                - timedelta(seconds=10),
            },
        )

        self.env["device.device"]._cron_check_health()

        self.assertEqual(device.connection_state, "disconnected")

    def test_every_transport_verb_is_implemented(self):
        device = self._make_device(identifier="WS-VERBS")
        for verb in ("connect", "disconnect", "read_data"):
            self.assertIsNotNone(
                device._transport_method(verb),
                f"websocket must implement {verb}",
            )


@tagged("post_install", "-at_install")
class TestWebsocketStream(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {
                "name": "WebSocket Stream Config",
                "auth_type": "bearer",
                "ws_ping_interval": 20,
            }
        )
        cls.config.sudo().auth_token = "t0ken"
        cls.device = cls.env["device.device"].create(
            {
                "name": "Feed",
                "identifier": "WS-FEED",
                "config_id": cls.config.id,
                "comm_protocol": "websocket",
                "endpoint": "feed.example",
                "port": 8080,
                "http_endpoint_path": "live",
            }
        )

    def test_the_device_carries_a_stream_that_says_how_to_dial(self):
        stream = self.device.stream_id
        self.assertEqual(stream.protocol, "websocket")
        self.assertEqual(stream.url, "ws://feed.example:8080/live")
        self.assertEqual(stream.options, {"auth": "bearer"})
        self.assertEqual(stream.credential_id, self.config.sudo().credential_id)
        self.assertFalse(stream.login)
        self.assertEqual(stream.heartbeat_seconds, 20)
        self.assertEqual(
            (stream.res_model, stream.res_id), ("device.device", self.device.id)
        )

    def test_a_basic_profile_names_its_login(self):
        self.config.write({"auth_type": "basic", "auth_username": "feed"})
        self.device.config_id = self.config
        self.device._sync_stream()
        stream = self.device.stream_id
        self.assertEqual((stream.options, stream.login), ({"auth": "basic"}, "feed"))

    def test_a_changed_path_changes_the_url(self):
        self.device.http_endpoint_path = "/other"
        self.assertEqual(self.device.stream_id.url, "ws://feed.example:8080/other")

    def test_connect_and_disconnect_start_and_stop_the_stream(self):
        self.device.websocket_disconnect()
        self.assertFalse(self.device.stream_id.active)
        self.device.action_connect()
        self.assertTrue(self.device.stream_id.active)

    def test_a_frame_is_a_data_point(self):
        self.device._on_stream_frame(
            self.device.stream_id, b'{"v": 1}', {"binary": False}
        )
        point = self.env["device.data.log"].search(
            [("device_id", "=", self.device.id)], order="id desc", limit=1
        )
        self.assertEqual(point.value_json, {"v": 1})

    def test_the_startup_reset_leaves_the_device_to_its_stream(self):
        self.device._set_connection_state("connected", False)
        self.env["device.device"]._register_hook()
        self.assertEqual(self.device.connection_state, "connected")
