from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


class TestRemoteDeviceMqttEndpoint(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create({"name": "MQTT Display Config"})

    def _create_device(self, **overrides):
        vals = {
            "name": "MQTT Display Device",
            "identifier": "MQTT-DISP-001",
            "config_id": self.config.id,
            "comm_protocol": "mqtt",
            "endpoint": "mqtt.example.com",
        }
        vals.update(overrides)
        return self.env["device.device"].create(vals)

    def test_display_endpoint_names_the_scheme_and_the_default_port(self):
        device = self._create_device()

        self.assertIn("mqtt://", device.display_endpoint)
        self.assertIn(":1883", device.display_endpoint)

    def test_tls_moves_the_default_port(self):
        self.config.mqtt_use_tls = True
        device = self._create_device(identifier="MQTT-DISP-002")

        self.assertEqual(device._protocol_default_port(), 8883)

    def test_mqtt_is_a_persistent_and_streamed_protocol(self):
        Device = self.env["device.device"]
        self.assertIn("mqtt", Device._persistent_protocols())
        self.assertIn("mqtt", Device._streamed_protocols())


@tagged("post_install", "-at_install")
class TestRemoteDeviceMqttStream(DeviceTransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {
                "name": "MQTT Stream Config",
                "auth_type": "basic",
                "auth_username": "scale",
                "mqtt_qos": "2",
                "mqtt_use_tls": True,
                "mqtt_session_expiry_interval": 600,
                "mqtt_subscribe_topics": "scale/+/weight\nscale/status\n",
                "mqtt_publish_topic": "scale/cmd",
            }
        )
        cls.config.sudo().auth_password = "s3cret"
        cls.device = cls.env["device.device"].create(
            {
                "name": "Scale 7",
                "identifier": "SCALE-7",
                "config_id": cls.config.id,
                "comm_protocol": "mqtt",
                "endpoint": "broker.example",
                "port": 8884,
            }
        )

    def test_deleting_a_hierarchy_removes_part_streams_and_pending_commands(self):
        part = self.device.copy(
            {"identifier": "PART-STREAM", "parent_id": self.device.id}
        )
        part.active = False
        stream = part.stream_id
        command = stream.send("pending command")
        self.assertTrue(command.exists())

        self.device.unlink()

        self.assertFalse(part.exists())
        self.assertFalse(stream.exists())
        self.assertFalse(command.exists())

    def test_probe_reports_a_legacy_orphan_stream_without_deleting_it(self):
        stream = self.device.stream_id
        self.env.cr.execute("DELETE FROM device_device WHERE id = %s", [self.device.id])
        report = self.env["device.device"]._probe_integrity()
        self.assertIn(stream.id, report["orphan_streams"]["ids"])
        self.assertTrue(stream.exists())

    def test_the_device_carries_a_stream_that_says_how_to_dial(self):
        stream = self.device.stream_id
        self.assertTrue(stream, "an MQTT device gets its stream at create")
        self.assertEqual(stream.protocol, "mqtt")
        self.assertEqual(stream.url, "mqtts://broker.example:8884")
        self.assertEqual(stream.login, "scale")
        self.assertEqual(stream.credential_id, self.config.sudo().credential_id)
        self.assertEqual(
            stream.subscriptions, {"topics": ["scale/+/weight", "scale/status"]}
        )
        self.assertEqual(
            stream.options,
            {
                "qos": 2,
                "client_id": "SCALE-7",
                "publish_topic": "scale/cmd",
                "session_expiry_interval": 600,
            },
        )
        self.assertEqual(
            (stream.res_model, stream.res_id), ("device.device", self.device.id)
        )
        self.assertEqual(stream.name, "Scale 7 (mqtt)")

    def test_a_changed_device_changes_its_stream(self):
        self.device.write({"mqtt_subscribe_topics": "only/this", "port": 1883})
        stream = self.device.stream_id
        self.assertEqual(stream.subscriptions, {"topics": ["only/this"]})
        self.assertEqual(stream.url, "mqtts://broker.example:1883")

    def test_a_changed_profile_changes_every_device_s_stream(self):
        self.config.write({"mqtt_subscribe_topics": "profile/topic", "mqtt_qos": "0"})
        stream = self.device.stream_id
        self.assertEqual(stream.subscriptions, {"topics": ["profile/topic"]})
        self.assertEqual(stream.options["qos"], 0)

    def test_connect_and_disconnect_start_and_stop_the_stream(self):
        self.device.mqtt_disconnect()
        self.assertFalse(self.device.stream_id.active)
        self.assertEqual(self.device.connection_state, "disconnected")
        self.device.action_connect()
        self.assertTrue(self.device.stream_id.active)

    def test_an_archived_device_stops_its_stream(self):
        self.device.active = False
        self.assertFalse(self.device.stream_id.active)

    def test_a_device_of_another_protocol_has_no_stream(self):
        http_device = self.env["device.device"].create(
            {
                "name": "Poller",
                "identifier": "HTTP-1",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "endpoint": "poller.example",
            }
        )
        self.assertFalse(http_device.stream_id)

    def test_a_frame_is_a_data_point_of_the_device(self):
        self.device._on_stream_frame(
            self.device.stream_id,
            b'{"kg": 12.5}',
            {"topic": "scale/7/weight", "qos": 2},
        )
        point = self.env["device.data.log"].search(
            [("device_id", "=", self.device.id)], order="id desc", limit=1
        )
        self.assertEqual(point.value_json, {"kg": 12.5})
        self.assertEqual(point.source_topic, "scale/7/weight")
        self.assertEqual(self.device.connection_state, "connected")

    def test_the_stream_s_state_is_the_device_s(self):
        stream = self.device.stream_id
        self.device._on_stream_state(stream, "open", None)
        self.assertEqual(self.device.connection_state, "connected")
        self.device._on_stream_state(stream, "backoff", "the connection dropped")
        self.assertEqual(
            (self.device.connection_state, self.device.connection_state_message),
            ("error", "the connection dropped"),
        )
        self.device._on_stream_state(stream, "stopped", None)
        self.assertEqual(self.device.connection_state, "disconnected")

    def test_read_only_device_user_cannot_queue_commands(self):
        reader = new_test_user(
            self.env, login="mqtt_read_only", groups="device.group_device_user"
        )
        device = self.device.with_user(reader)
        self.assertEqual(device.name, "Scale 7")
        with self.assertRaises(AccessError), self.env.cr.savepoint():
            device.mqtt_send(b"tare", topic="scale/7/do")

    def test_read_only_device_user_cannot_control_stream_lifecycle(self):
        reader = new_test_user(
            self.env, login="mqtt_lifecycle_reader", groups="device.group_device_user"
        )
        device = self.device.with_user(reader)
        for method in (
            "mqtt_connect",
            "mqtt_disconnect",
            "mqtt_read_data",
            "action_connect",
            "action_disconnect",
            "action_read_data",
        ):
            with self.subTest(method=method), self.assertRaises(AccessError):
                getattr(device, method)()

    def test_default_mqtt_identity_follows_device_identifier(self):
        self.device.identifier = "SCALE-RENAMED"
        self.assertEqual(self.device.stream_id.options["client_id"], "SCALE-RENAMED")

    def test_manager_cannot_send_to_a_device_outside_their_company(self):
        manager = new_test_user(
            self.env, login="mqtt_scoped_manager", groups="device.group_device_manager"
        )
        company = self.env["res.company"].create({"name": "Other stream tenant"})
        self.device.company_id = company
        with self.assertRaises(AccessError):
            self.device.with_user(manager).mqtt_send(b"tare")

    def test_stream_follows_device_company(self):
        company = self.env["res.company"].create({"name": "Stream destination"})
        self.device.company_id = company
        self.assertEqual(self.device.stream_id.company_id, company)

    def test_a_send_is_a_row_of_the_stream_s_outbox(self):
        outbox = self.device.mqtt_send(b"tare", topic="scale/7/do", qos=1)
        self.assertEqual(outbox.stream_id, self.device.stream_id)
        self.assertEqual(
            (outbox.payload, outbox.meta), ("tare", {"topic": "scale/7/do", "qos": 1})
        )

    def test_the_startup_reset_leaves_a_streamed_device_alone(self):
        self.device._set_connection_state("connected", False)
        self.env["device.device"]._register_hook()
        self.assertEqual(self.device.connection_state, "connected")

    def test_the_health_check_cron_is_gone(self):
        self.assertFalse(
            self.env.ref(
                "device_mqtt.ir_cron_mqtt_health_check", raise_if_not_found=False
            )
        )
        self.assertFalse(hasattr(self.env["device.device"], "_cron_mqtt_health_check"))
