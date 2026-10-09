from datetime import datetime

from odoo.libs.json import dumps_bytes as json_dumps_bytes
from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceHttpCase, NarrowedReceiver


@tagged("post_install", "-at_install")
class TestMobileLocation(DeviceHttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Mobile Test Config",
                "auth_type": "bearer",
                "auth_token": "mobile_token_123",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Test Phone",
                "identifier": "PHONE-001",
                "config_id": cls.config.id,
                "comm_protocol": "https",
                "endpoint": "companion-app",
                "company_id": cls.company.id,
                "device_category_id": cls.env.ref(
                    "device_mobile.device_category_mobile_phone"
                ).id,
            }
        )
        cls.token = cls.device.credential_id.credential_value

    def _push(self, body, token=None):
        return self.url_open(
            "/remote/mobile/PHONE-001/location",
            data=json_dumps_bytes(body),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token or self.token}",
            },
        )

    def _logs(self):
        return self.env["device.data.log.gps"].search(
            [("device_id", "=", self.device.id)]
        )

    def test_push_single_fix(self):
        resp = self._push(
            {
                "latitude": 19.4326,
                "longitude": -99.1332,
                "speed": 12.5,
                "accuracy": 8.0,
                "heading": 90.0,
                "altitude": 2240.0,
                "battery": 87,
                "timestamp": "2026-07-28T14:00:00Z",
            }
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["accepted"], 1)
        log = self._logs()
        self.assertEqual(len(log), 1)
        self.assertAlmostEqual(log.latitude, 19.4326, places=4)
        self.assertAlmostEqual(log.longitude, -99.1332, places=4)
        self.assertAlmostEqual(log.speed, 45.0, places=2)
        self.assertAlmostEqual(log.battery_level, 87.0, places=2)
        self.assertTrue(log.movement)
        self.assertEqual(log.timestamp.hour, 14)

    def test_epoch_millis_timestamp_is_the_fix_time(self):
        resp = self._push(
            {
                "points": [
                    {
                        "latitude": 19.4326,
                        "longitude": -99.1332,
                        "timestamp": 1751000000000,
                    }
                ]
            }
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self._logs().timestamp,
            datetime(2025, 6, 27, 4, 53, 20),
        )

    def test_push_batch_and_skip_invalid(self):
        resp = self._push(
            {
                "points": [
                    {"latitude": 19.0, "longitude": -99.0},
                    {"latitude": 19.1, "longitude": -99.1},
                    {"latitude": 999.0, "longitude": -99.2},
                    {"speed": 5.0},
                ]
            }
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["accepted"], 2)
        self.assertEqual(payload["skipped"], 2)
        self.assertEqual(payload["skipped_indexes"], [2, 3])
        self.assertEqual(len(self._logs()), 2)

    def test_bad_token_rejected(self):
        resp = self._push({"latitude": 19.0, "longitude": -99.0}, token="wrong-token")
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(self._logs())

    def test_connection_state_becomes_connected(self):
        self.assertNotEqual(self.device.connection_state, "connected")
        self._push({"latitude": 19.0, "longitude": -99.0})
        self.device.invalidate_recordset(["connection_state"])
        self.assertEqual(self.device.connection_state, "connected")


@tagged("post_install", "-at_install")
class TestMobileLocationWithoutSu(NarrowedReceiver, TestMobileLocation):
    pass
