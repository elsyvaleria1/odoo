from odoo.exceptions import UserError
from odoo.tests import new_test_user, tagged

from .common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestInboundTokenAction(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = new_test_user(
            cls.env, login="device_token_manager", groups="device.group_device_manager"
        )

    def _generate(self, device):
        action = type(device).action_generate_inbound_token.__wrapped__
        return action(device.with_user(self.manager))

    def _generated_token(self, device):
        return self._generate(device)["params"]["message"].split("\n", 1)[0]

    def test_the_token_shown_once_is_the_one_the_device_must_send(self):
        device = self._create_device_device(identifier="TOKEN-1", auth_type="bearer")
        action = self._generate(device)
        token = action["params"]["message"].split("\n", 1)[0]
        self.assertEqual(action["tag"], "display_notification")
        self.assertTrue(action["params"]["sticky"])
        self.assertIn("TOKEN-1", action["params"]["message"])
        self.assertEqual(len(token), 64)
        self.assertTrue(device.is_valid_token(token))

    def test_a_new_token_replaces_the_one_before_it(self):
        device = self._create_device_device(identifier="TOKEN-2", auth_type="bearer")
        before = self._device_token(device)
        token = self._generated_token(device)
        self.assertNotEqual(token, before)
        self.assertTrue(device.is_valid_token(token))
        self.assertFalse(device.is_valid_token(before))

    def test_a_device_without_a_credential_is_given_one(self):
        device = self._create_device_device(identifier="TOKEN-3", auth_type="bearer")
        device.sudo().credential_id = False
        token = self._generated_token(device)
        self.assertTrue(device.credential_id)
        self.assertTrue(device.inbound_token_set)
        self.assertTrue(device.is_valid_token(token))

    def test_a_device_that_sends_no_token_is_not_given_one(self):
        device = self._create_device_device(identifier="TOKEN-4", auth_type="none")
        with self.assertRaises(UserError):
            self._generate(device)

    def test_the_action_asks_for_the_password_first(self):
        self.assertTrue(
            getattr(
                type(self.env["device.device"]).action_generate_inbound_token,
                "__has_check_identity",
                False,
            )
        )

    def test_a_device_saved_from_the_form_gets_a_credential(self):
        device = self._create_device_device(identifier="FORM-1", credential_id=False)
        self.assertTrue(device.credential_id)
        self.assertTrue(self._device_token(device))
