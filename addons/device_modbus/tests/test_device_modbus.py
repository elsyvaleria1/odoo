from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


class _DeviceFixture(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Modbus Config",
                "modbus_unit_id": 3,
                "modbus_register_type": "input",
                "http_timeout": 4,
            }
        )

    def _make_device(self, **overrides):
        vals = {
            "name": "Modbus Device",
            "identifier": "MODBUS-DEFAULT",
            "config_id": self.config.id,
            "comm_protocol": "modbus_tcp",
            "endpoint": "10.0.0.1",
        }
        vals.update(overrides)
        return self.env["device.device"].create(vals)


class TestDeviceModbus(_DeviceFixture):
    def test_the_module_contributes_both_protocol_values(self):
        selection = dict(
            self.env["device.device"]
            ._fields["comm_protocol"]
            .get_description(self.env)["selection"]
        )
        self.assertIn("modbus_tcp", selection)
        self.assertIn("modbus_rtu", selection)

    def test_modbus_is_a_streamed_protocol_not_a_polled_one(self):
        device_model = self.env["device.device"]
        for protocol in ("modbus_tcp", "modbus_rtu"):
            self.assertIn(protocol, device_model._persistent_protocols())
            self.assertIn(protocol, device_model._streamed_protocols())
            self.assertNotIn(protocol, device_model._polled_protocols())

    def test_display_endpoint_and_default_port(self):
        device = self._make_device(
            identifier="MODBUS-DISP",
            endpoint="192.168.1.200",
            port=502,
        )
        self.assertEqual(device.display_endpoint, "192.168.1.200:502")
        self.assertEqual(device._protocol_default_port(), 502)

    def test_demo_generate_modbus_tcp_data(self):
        device = self._make_device(
            identifier="DEMO-MODBUS-001",
            endpoint="192.168.1.200",
            is_demo=True,
            modbus_register_count=5,
        )

        data = device._demo_generate_modbus_tcp_data()

        self.assertTrue(data["demo"])
        self.assertEqual(data["count"], 5)
        self.assertEqual(len(data["values"]), 5)


@tagged("post_install", "-at_install")
class TestModbusStream(_DeviceFixture):
    def test_reader_cannot_start_stream_through_measurement_read(self):
        reader = new_test_user(
            self.env, login="modbus_reader", groups="device.group_device_user"
        )
        device = self._make_device().with_user(reader)
        with self.assertRaises(AccessError):
            device.modbus_tcp_read_data()

    def test_a_tcp_device_s_stream_names_its_registers(self):
        device = self._make_device(
            identifier="REG-MODBUS",
            modbus_register_start=7,
            modbus_register_count=4,
            modbus_poll_seconds=15,
        )
        stream = device.stream_id
        self.assertEqual(stream.protocol, "modbus")
        self.assertEqual(stream.url, "modbus://10.0.0.1:502")
        self.assertEqual(
            stream.subscriptions,
            {
                "unit_id": 3,
                "registers": [{"type": "input", "start": 7, "count": 4}],
            },
        )
        self.assertEqual(stream.options, {"timeout": 4})
        self.assertEqual(stream.heartbeat_seconds, 15)

    def test_register_count_is_capped_at_the_protocol_maximum(self):
        device = self._make_device(identifier="REG-CAP", modbus_register_count=500)
        self.assertEqual(device.stream_id.subscriptions["registers"][0]["count"], 125)

    def test_a_serial_device_s_stream_names_the_port_and_the_baud_rate(self):
        device = self._make_device(
            identifier="RTU-1",
            comm_protocol="modbus_rtu",
            endpoint="/dev/ttyUSB0",
            port=19200,
        )
        self.assertEqual(
            device.stream_id.url, "modbus+rtu:///dev/ttyUSB0?baudrate=19200"
        )
        self.assertEqual(device.display_endpoint, "/dev/ttyUSB0 @ 19200 baud")

    def test_a_reading_is_a_data_point_with_its_registers_named(self):
        device = self._make_device(identifier="READ-1", modbus_register_start=7)
        device._on_stream_frame(
            device.stream_id,
            b'{"unit_id": 3, "register_type": "input", "start_address": 7, "count": 2, "values": [11, 22]}',
            {"topic": "input/7"},
        )
        point = self.env["device.data.log"].search(
            [("device_id", "=", device.id)], order="id desc", limit=1
        )
        self.assertEqual(point.value_json["register_7"], 11)
        self.assertEqual(point.value_json["register_8"], 22)
        self.assertEqual(point.source_topic, "modbus://10.0.0.1:502")
        self.assertEqual(device.connection_state, "connected")

    def test_every_transport_verb_starts_or_stops_the_stream(self):
        device = self._make_device(identifier="VERBS-1")
        device.modbus_tcp_disconnect()
        self.assertFalse(device.stream_id.active)
        self.assertTrue(device.modbus_tcp_connect())
        self.assertTrue(device.stream_id.active)
        self.assertEqual(device.modbus_tcp_read_data(), {})

    def test_a_write_is_a_frame_on_the_outbox(self):
        device = self._make_device(identifier="WRITE-1")
        outbox = device.modbus_write(40, 7)
        self.assertEqual(outbox.stream_id, device.stream_id)
        self.assertIn('"address": 40', outbox.payload)
        self.assertIn('"unit_id": 3', outbox.payload)
