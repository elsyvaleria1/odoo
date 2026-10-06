from datetime import datetime

from odoo.libs.json import loads as json_loads
from odoo.tests import common


class TestGpsLiveBroadcast(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.config = cls.env["device.profile"].create(
            {
                "name": "Test GPS Config",
                "auth_type": "bearer",
                "auth_token": "test_token_gps",
            }
        )

        cls.group = cls.env.ref("device.group_device_user")

        cls.device = cls.env["device.device"].create(
            {
                "name": "Test GPS Device",
                "identifier": "GPS-LIVE-001",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.200",
            }
        )

    def _create_gps_log(self, latitude=19.4326, longitude=-99.1332, speed=60.0):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "latitude": latitude,
                "longitude": longitude,
                "speed": speed,
                "timestamp": datetime.now(),
                "data_type": "json",
                "source": "webhook",
            }
        )

    def test_write_log_gps_last_id_sends_bus_notification(self):
        gps_log = self._create_gps_log(latitude=19.4326, longitude=-99.1332, speed=55.0)

        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

        self.device.write({"log_gps_last_id": gps_log.id})
        self.env.cr.precommit.run()

        bus_records = self.env["bus.bus"].sudo().search([])
        messages = [r.message for r in bus_records]
        gps_messages = [m for m in messages if "device_device/gps_position" in m]
        self.assertTrue(
            gps_messages,
            "Expected a bus notification with type 'device_device/gps_position'",
        )

    def test_bus_payload_contains_position_data(self):
        gps_log = self._create_gps_log(
            latitude=20.6597, longitude=-103.3496, speed=80.5
        )

        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

        self.device.write({"log_gps_last_id": gps_log.id})
        self.env.cr.precommit.run()

        bus_records = self.env["bus.bus"].sudo().search([])
        for record in bus_records:
            msg = json_loads(record.message)
            if msg.get("type") == "device_device/gps_position":
                payload = msg["payload"]
                self.assertEqual(payload["device_id"], self.device.id)
                self.assertAlmostEqual(payload["latitude"], 20.6597, places=4)
                self.assertAlmostEqual(payload["longitude"], -103.3496, places=4)
                self.assertAlmostEqual(payload["speed"], 80.5, places=1)
                self.assertTrue(payload["timestamp"])
                return

        self.fail("No GPS position bus notification found")

    def test_write_without_log_gps_last_id_no_notification(self):
        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

        self.device.write({"name": "Renamed Device"})
        self.env.cr.precommit.run()

        bus_records = self.env["bus.bus"].sudo().search([])
        messages = [r.message for r in bus_records]
        gps_messages = [m for m in messages if "device_device/gps_position" in m]
        self.assertFalse(
            gps_messages,
            "No GPS notification should be sent when log_gps_last_id is not changed",
        )

    def test_write_log_gps_last_id_false_no_notification(self):
        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

        self.device.write({"log_gps_last_id": False})
        self.env.cr.precommit.run()

        bus_records = self.env["bus.bus"].sudo().search([])
        messages = [r.message for r in bus_records]
        gps_messages = [m for m in messages if "device_device/gps_position" in m]
        self.assertFalse(
            gps_messages,
            "No GPS notification should be sent when log_gps_last_id is set to False",
        )

    def test_broadcast_multiple_devices(self):
        device2 = self.env["device.device"].create(
            {
                "name": "Test GPS Device 2",
                "identifier": "GPS-LIVE-002",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.201",
            }
        )

        log1 = self._create_gps_log(latitude=19.0, longitude=-99.0)
        log2 = self.env["device.data.log.gps"].create(
            {
                "device_id": device2.id,
                "latitude": 20.0,
                "longitude": -100.0,
                "speed": 45.0,
                "timestamp": datetime.now(),
                "data_type": "json",
                "source": "webhook",
            }
        )

        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

        self.device.write({"log_gps_last_id": log1.id})
        device2.write({"log_gps_last_id": log2.id})
        self.env.cr.precommit.run()

        bus_records = self.env["bus.bus"].sudo().search([])
        gps_payloads = []
        for record in bus_records:
            msg = json_loads(record.message)
            if msg.get("type") == "device_device/gps_position":
                gps_payloads.append(msg["payload"])

        device_ids = {p["device_id"] for p in gps_payloads}
        self.assertIn(self.device.id, device_ids)
        self.assertIn(device2.id, device_ids)

    def test_the_pointer_job_broadcasts_even_though_it_writes_raw_sql(self):
        self._create_gps_log()
        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

        self.env["device.device"]._cron_refresh_gps_pointers()
        self.env.cr.precommit.run()

        sent = [
            json_loads(record.message)
            for record in self.env["bus.bus"].sudo().search([])
        ]
        self.assertTrue(
            [m for m in sent if m.get("type") == "device_device/gps_position"],
            "the pointer job moved log_gps_last_id without telling the map",
        )

    def test_broadcast_targets_the_channel_the_websocket_subscribes_to(self):
        company = self.device.company_id or self.env.company
        expected = [self.env.cr.dbname, "res.groups", self.group.id, company.id]

        gps_log = self._create_gps_log()

        self.env.cr.precommit.run()
        self.env["bus.bus"].sudo().search([]).unlink()

        self.device.write({"log_gps_last_id": gps_log.id})
        self.env.cr.precommit.run()

        bus_records = self.env["bus.bus"].sudo().search([])
        for record in bus_records:
            msg = json_loads(record.message)
            if msg.get("type") == "device_device/gps_position":
                self.assertEqual(json_loads(record.channel), expected)
                return

        self.fail("No GPS position bus notification found")
