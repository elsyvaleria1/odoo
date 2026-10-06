from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.service.model import call_kw
from odoo.tests import new_test_user

from odoo.addons.device.tests.common import DeviceTransactionCase

DEVICE_USERS = [
    {"employeeNo": "4242", "name": "Stranger", "RightPlan": [{"planTemplateNo": "1"}]}
]


class TestFetchUsersRpcBoundary(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.device = cls.env["device.device"].create(
            {
                "name": "Door",
                "identifier": "TEST-FETCH-001",
                "config_id": cls.env.ref(
                    "device_access_control.device_profile_isapi_access"
                ).id,
                "is_demo": True,
            }
        )
        cls.reader = new_test_user(
            cls.env,
            login="door_reader",
            groups="base.group_user,device.group_device_user",
        )

    def _device_users(self):
        return self.env["access.device.user"].search_count(
            [("device_id", "=", self.device.id)]
        )

    def test_a_reader_of_the_device_imports_no_access_user(self):
        self.assertTrue(self.device.with_user(self.reader).has_access("read"))
        with (
            patch.object(
                type(self.device), "_get_all_device_users", return_value=DEVICE_USERS
            ) as fetch,
            self.assertRaises(AccessError),
        ):
            call_kw(
                self.env["device.device"].with_user(self.reader),
                "action_fetch_users",
                [[self.device.id]],
                {},
            )
        fetch.assert_not_called()
        self.assertEqual(self._device_users(), 0)

    def test_a_system_user_imports_the_device_users(self):
        with patch.object(
            type(self.device), "_get_all_device_users", return_value=DEVICE_USERS
        ):
            self.device.with_user(self.env.ref("base.user_admin")).action_fetch_users()
        self.assertEqual(self._device_users(), 1)
