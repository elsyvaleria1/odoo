import os
import unittest
from unittest.mock import MagicMock, patch

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, new_test_user, tagged

from ..models.bus import channel_with_db, json_dump
from ..models.ir_websocket import MAX_CHANNEL_LENGTH, MAX_SUBSCRIBED_CHANNELS
from ..tools.channel_capability import channel_capability, channel_target
from .common import TEST_CHANNEL, WebsocketCase, channel_key, channel_keys


@tagged("-at_install", "post_install")
@unittest.skipIf(
    os.getenv("ODOO_FAKETIME_TEST_MODE"), "This test cannot work with faketime"
)
class TestIrWebsocket(WebsocketCase):
    def test_only_allow_string_channels_from_frontend(self):
        with self.assertLogs("odoo.addons.bus.websocket", level="WARNING") as log:
            ws = self.websocket_connect()
            self.subscribe(
                ws,
                [("odoo", "discuss.channel", 5)],
                self.env["bus.bus"]._bus_last_id(),
                wait_for_dispatch=False,
            )
            ws.ping()
            ws.recv_data_frame(control_frame=True)
        self.assertIn("bus.Bus only string channels are allowed.", log.output[0])

    def test_a_watermark_past_the_newest_row_is_reset_on_its_socket(self):
        newest = self.env["bus.bus"]._bus_last_id()
        ws = self.websocket_connect()
        ws.send(
            json_dumps(
                {
                    "event_name": "subscribe",
                    "data": {
                        "channels": [],
                        "last": newest + 1000,
                        "report_watermark_reset": True,
                    },
                }
            )
        )
        self.assertEqual(
            json_loads(ws.recv()), {"event": "watermark_reset", "last": newest}
        )

    def test_a_client_that_does_not_ask_is_not_told_of_a_reset(self):
        newest = self.env["bus.bus"]._bus_last_id()
        ws = self.websocket_connect()
        ws.send(
            json_dumps(
                {
                    "event_name": "subscribe",
                    "data": {"channels": [], "last": newest + 1000},
                }
            )
        )
        ws.ping()
        _opcode, frame = ws.recv_data_frame(control_frame=True)
        self.assertEqual(frame.opcode, 10)

    def test_build_bus_channel_list(self):
        test_user = new_test_user(
            self.env,
            login="test_user",
            password="Password!1",
            groups="base.group_system",
        )
        mock_wsrequest = MagicMock()
        mock_wsrequest.session.uid = test_user.id
        with patch("odoo.addons.bus.models.ir_websocket.wsrequest", new=mock_wsrequest):
            ir_websocket_model = self.env["ir.websocket"].with_user(test_user)
            channels = set(
                channel_keys(
                    self.env,
                    ir_websocket_model._get_bus_channels(["test_channel"]),
                )
            )
        expected_channels = set(
            channel_keys(
                self.env,
                [
                    test_user.partner_id,
                    self.env.ref("base.group_system"),
                    self.env.ref("base.group_user"),
                ],
            )
        )
        self.assertTrue(
            expected_channels.issubset(channels),
            f"The channels list is missing some expected values: {expected_channels - channels}.",
        )


@tagged("-at_install", "post_install")
class TestBuildBusChannelList(TransactionCase):
    def test_callable_without_any_request_bound(self):
        keys = channel_keys(
            self.env, self.env["ir.websocket"]._get_bus_channels(["custom"])
        )
        self.assertNotIn(channel_key(self.env, "custom"), keys)
        self.assertIn(channel_key(self.env, "broadcast"), keys)

    def test_logged_in_user_gets_their_partner_channel(self):
        user = new_test_user(self.env, login="bus_chan_user")
        keys = channel_keys(
            self.env,
            self.env["ir.websocket"].with_user(user)._get_bus_channels([]),
        )
        self.assertIn(channel_key(self.env, user.partner_id), keys)

    def test_public_user_gets_no_partner_channel(self):
        public = self.env.ref("base.public_user")
        keys = channel_keys(
            self.env,
            self.env["ir.websocket"].with_user(public)._get_bus_channels([]),
        )
        self.assertNotIn(channel_key(self.env, public.partner_id), keys)


@tagged("-at_install", "post_install")
class TestSubscribeDataValidation(TransactionCase):
    def test_channel_count_is_capped(self):
        channels = [f"c{i}" for i in range(MAX_SUBSCRIBED_CHANNELS + 1)]
        with self.assertRaises(ValueError) as err:
            self.env["ir.websocket"]._prepare_subscribe_data(channels, 0)
        self.assertIn("limited to", str(err.exception))
        self.env["ir.websocket"]._prepare_subscribe_data(
            channels[:MAX_SUBSCRIBED_CHANNELS], 0
        )

    def test_channel_length_is_capped(self):
        with self.assertRaises(ValueError) as err:
            self.env["ir.websocket"]._prepare_subscribe_data(
                ["x" * (MAX_CHANNEL_LENGTH + 1)], 0
            )
        self.assertIn("characters", str(err.exception))
        self.env["ir.websocket"]._prepare_subscribe_data(["x" * MAX_CHANNEL_LENGTH], 0)

    def test_last_zero_skips_the_max_id_query(self):
        bus = self.env["bus.bus"]
        with patch.object(type(bus), "_bus_last_id", wraps=bus._bus_last_id) as last_id:
            self.env["ir.websocket"]._prepare_subscribe_data([], 0)
            last_id.assert_not_called()
            self.env["ir.websocket"]._prepare_subscribe_data([], 1)
            last_id.assert_called_once()

    def test_out_of_range_last_is_clamped(self):
        newest = self.env["bus.bus"].sudo()._bus_last_id()
        data = self.env["ir.websocket"]._prepare_subscribe_data([], newest + 1000)
        self.assertEqual(data["last"], 0)
        self.assertEqual(data["watermark_reset"], newest)

    def test_in_range_last_is_preserved(self):
        self.env["bus.bus"]._sendone("some_channel", "type", "message")
        self.env.cr.precommit.run()
        in_range = self.env["bus.bus"].sudo()._bus_last_id()
        data = self.env["ir.websocket"]._prepare_subscribe_data([], in_range)
        self.assertEqual(data["last"], in_range)
        self.assertIsNone(data["watermark_reset"])

    def test_negative_last_is_clamped_to_zero(self):
        data = self.env["ir.websocket"]._prepare_subscribe_data([], -5)
        self.assertEqual(data["last"], 0)

    def test_a_name_the_client_makes_up_is_refused(self):
        capability = channel_capability(self.env, TEST_CHANNEL, "7")
        data = self.env["ir.websocket"]._prepare_subscribe_data(
            ["made_up", "broadcast", capability], 0
        )
        channels = data["channels"]
        self.assertEqual([c for c in channels if isinstance(c, str)], [])
        self.assertIn(channel_target(self.env, TEST_CHANNEL, "7"), channels)
        self.assertIn(channel_with_db(self.env.cr.dbname, "broadcast"), channels)
        self.assertIn(self.env.user.partner_id, channels)


@tagged("-at_install", "post_install")
class TestBusChannelRoutes(TransactionCase):
    def test_a_named_channel_is_routed_and_one_every_subscriber_gets_is_not(self):
        user = new_test_user(self.env, login="bus_routes_user")
        partner = self.env["res.partner"].create({"name": "Routed"})
        websocket = self.env["ir.websocket"].with_user(user)
        opened = {"named": [partner], "own-partner": [user.partner_id], "none": []}
        with patch.object(
            type(self.env["ir.websocket"]), "_bus_channels_by_name", return_value=opened
        ):
            data = websocket._prepare_subscribe_data(list(opened), 0)
        db = self.env.cr.dbname
        self.assertEqual(
            dict(data["routes"]),
            {json_dump(channel_with_db(db, partner)): ("named",)},
        )
        self.assertIn(partner, data["channels"])
        self.assertIn(user.partner_id, data["channels"])

    def test_a_channel_two_names_open_is_routed_by_both(self):
        partner = self.env["res.partner"].create({"name": "Shared"})
        opened = {"b": [partner], "a": [partner]}
        with patch.object(
            type(self.env["ir.websocket"]), "_bus_channels_by_name", return_value=opened
        ):
            data = self.env["ir.websocket"]._prepare_subscribe_data(list(opened), 0)
        self.assertEqual(list(dict(data["routes"]).values()), [("a", "b")])
