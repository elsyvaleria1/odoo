from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.libs.json import loads as json_loads

from odoo.addons.device.tests.common import DeviceTransactionCase


class TestAccessDeviceUserDelete(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls.env["device.device"].create(
            {
                "name": "Test Door",
                "identifier": "TEST-DELETE-001",
                "config_id": cls.env.ref(
                    "device_access_control.device_profile_isapi_access"
                ).id,
                "is_demo": True,
            }
        )
        cls.user = cls.env["access.device.user"].create(
            {
                "device_id": cls.device.id,
                "employee_no": "999",
                "access_profile": "tenant",
                "state": "synced",
            }
        )

    def test_delete_payload_uses_correct_key(self):
        captured = {}

        def fake_request(_self, _method, _path, data=None, **_kwargs):
            captured["data"] = data
            return '{"statusCode": 1, "statusString": "OK", "subStatusCode": "ok"}'

        with patch.object(type(self.device), "_isapi_request", fake_request):
            self.user._remove_user_from_device()

        payload = json_loads(captured["data"])
        self.assertIn("UserInfoDelCond", payload)
        self.assertNotIn("UserInfoDetail", payload)
        self.assertEqual(
            payload["UserInfoDelCond"]["EmployeeNoList"][0]["employeeNo"],
            "999",
        )

    def test_delete_raises_on_device_error(self):
        def fake_request(_self, _method, _path, data=None, **_kwargs):
            return (
                '{"statusCode": 6, "statusString": "Invalid Content",'
                ' "subStatusCode": "MessageParametersLack"}'
            )

        with patch.object(type(self.device), "_isapi_request", fake_request):
            with self.assertRaises(UserError):
                self.user._remove_user_from_device()

    def test_unlink_aborts_when_device_delete_fails(self):
        def fake_request(_self, _method, _path, data=None, **_kwargs):
            return '{"statusCode": 6, "statusString": "Invalid Content"}'

        with patch.object(type(self.device), "_isapi_request", fake_request):
            with self.assertRaises(UserError):
                self.user.unlink()
        self.assertTrue(self.user.exists())
