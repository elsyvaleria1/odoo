import os
from unittest.mock import patch

from odoo.libs import sealing
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAccessCredentialsSplit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        key_patcher = patch.dict(
            os.environ,
            sealing.rotated_environ("7ftr9ALjwK7f4IqWwnpFxWx4Wn8vetsznoGT3Oh46eU="),
        )
        key_patcher.start()
        cls.addClassCleanup(key_patcher.stop)
        cls.config = cls.env.ref("device_access_control.device_profile_isapi_access")
        cls.bearer_category = cls.env.ref("credential.credential_category_bearer_token")

    def _device(self, identifier, **vals):
        return self.env["device.device"].create(
            {
                "name": identifier,
                "identifier": identifier,
                "config_id": self.config.id,
                "device_category_id": self.env.ref(
                    "device_access_control.device_kind_access_control"
                ).id,
                "is_demo": True,
                **vals,
            }
        )

    def _panel_login(self):
        return self.env["credential.credential"].create(
            {
                "name": "Panel login",
                "category_id": self.env.ref(
                    "credential.credential_category_basic_auth"
                ).id,
                "username": "admin",
                "password": "panel-pass",
            }
        )

    def _legacy_ehome_credential(self):
        return self.env["credential.credential"].create(
            {
                "name": "Legacy EHOME",
                "category_id": self.env.ref(
                    "device_access_control.credential_category_ehome"
                ).id,
                "api_key": "EHOME-PANEL-1",
                "api_secret": "http://192.168.1.9:8085",
            }
        )

    def test_a_new_direct_device_gets_an_inbound_token_of_its_own(self):
        login = self._panel_login()

        device = self._device(
            "SPLIT-DIRECT",
            access_connection_mode="direct",
            endpoint="192.168.1.50",
            dial_credential_id=login.id,
        )

        self.assertNotEqual(device.credential_id, login)
        self.assertEqual(device.credential_id.category_id, self.bearer_category)
        self.assertFalse(device.is_valid_token("panel-pass"))
        self.assertFalse(device.inbound_credential_shared)

    def test_the_ehome_device_id_is_configuration_not_an_inbound_token(self):
        device = self._device(
            "SPLIT-EHOME",
            access_connection_mode="ehome",
            ehome_device_id="EHOME-PANEL-1",
            ehome_bridge_url="http://192.168.1.9:8085",
        )

        self.assertFalse(device.is_valid_token("EHOME-PANEL-1"))
        self.assertEqual(device._require_ehome_device_id(), "EHOME-PANEL-1")
        self.assertEqual(device._get_ehome_api_url(), "http://192.168.1.9:8085")

    def test_a_legacy_ehome_device_is_adopted_flagged_and_rotatable(self):
        device = self._device(
            "LEGACY-EHOME",
            access_connection_mode="ehome",
            credential_id=self._legacy_ehome_credential().id,
        )

        device._adopt_legacy_access_credentials()

        self.assertEqual(device.ehome_device_id, "EHOME-PANEL-1")
        self.assertEqual(device.ehome_bridge_url, "http://192.168.1.9:8085")
        self.assertTrue(device.inbound_credential_shared)
        self.assertTrue(
            device.is_valid_token("EHOME-PANEL-1"),
            "adoption must not change the token a deployed bridge already sends",
        )

        device.action_rotate_inbound_token()

        self.assertFalse(device.inbound_credential_shared)
        self.assertFalse(device.is_valid_token("EHOME-PANEL-1"))

    def test_a_legacy_direct_device_login_moves_to_the_access_credential(self):
        login = self._panel_login()
        device = self._device(
            "LEGACY-DIRECT",
            access_connection_mode="direct",
            endpoint="192.168.1.51",
            credential_id=login.id,
        )

        device._adopt_legacy_access_credentials()

        self.assertEqual(device.dial_credential_id, login)
        self.assertTrue(device.inbound_credential_shared)
