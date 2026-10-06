import base64
from unittest.mock import patch

from odoo.exceptions import UserError

from odoo.addons.device.tests.common import DeviceTransactionCase

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01face\xff\xd9"


class TestAccessDeviceUserActions(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls.env["device.device"].create(
            {
                "name": "Test Door",
                "identifier": "TEST-ACTIONS-001",
                "config_id": cls.env.ref(
                    "device_access_control.device_profile_isapi_access"
                ).id,
                "access_connection_mode": "ehome",
                "ehome_device_id": "TEST-ACTIONS-001",
                "is_demo": True,
            }
        )
        cls.employee = cls.env["hr.employee"].create({"name": "Ana Door"})

    def setUp(self):
        super().setUp()
        self.requests = []

        def fake_request(_device, method, path, data=None, **_kwargs):
            self.requests.append((method, path, data))
            return '{"statusCode": 1, "statusString": "OK"}'

        patcher = patch.object(type(self.device), "_isapi_request", fake_request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_user_created_on_a_connected_device_is_synced(self):
        self.device.connection_state = "connected"
        user = self.env["access.device.user"].create(
            {"device_id": self.device.id, "employee_id": self.employee.id}
        )
        self.assertEqual(user.state, "synced")
        self.assertEqual(
            self.requests[0][:2],
            ("POST", "/ISAPI/AccessControl/UserInfo/Record?format=json"),
        )

    def test_sync_answers_with_a_notification(self):
        user = self.env["access.device.user"].create(
            {"device_id": self.device.id, "employee_id": self.employee.id}
        )
        action = user.action_sync_to_device()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(action["params"]["type"], "success")

    def test_an_uploaded_face_reaches_the_device_whole(self):
        user = self.env["access.device.user"].create(
            {
                "device_id": self.device.id,
                "employee_id": self.employee.id,
                "state": "synced",
                "face_photo": base64.b64encode(JPEG),
            }
        )
        action = user.action_capture_face()
        self.assertEqual(action["tag"], "display_notification")
        self.assertEqual(user.face_count, 1)
        method, path, body = self.requests[-1]
        self.assertEqual(
            (method, path), ("PUT", "/ISAPI/AccessControl/UserInfo/SetUp?format=json")
        )
        self.assertIn(JPEG, body)

    def test_a_face_without_photo_is_refused(self):
        user = self.env["access.device.user"].create(
            {
                "device_id": self.device.id,
                "employee_id": self.employee.id,
                "state": "synced",
            }
        )
        with self.assertRaises(UserError):
            user.action_capture_face()
        self.assertFalse(self.requests)
