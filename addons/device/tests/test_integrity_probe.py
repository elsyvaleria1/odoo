from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user


class TestDeviceIntegrityProbe(TransactionCase):
    def test_probe_finds_missing_company_without_mutating_device(self):
        device = self.env["device.device"].create(
            {
                "name": "Unscoped probe fixture",
                "identifier": "probe-unscoped",
                "company_id": False,
                "is_demo": True,
            }
        )
        self.env.flush_all()
        report = device._probe_integrity(limit=1)
        self.assertIn(device.id, report["missing_company"]["ids"])
        self.assertFalse(device.company_id)

    def test_probe_requires_administrator(self):
        user = new_test_user(self.env, login="device_probe", groups="base.group_user")
        with self.assertRaises(AccessError):
            self.env["device.device"].with_user(user)._probe_integrity()


class TestDeviceTransportAccess(TransactionCase):
    def test_http_verbs_require_write_before_network_or_state_changes(self):
        reader = new_test_user(
            self.env, login="http_device_reader", groups="device.group_device_user"
        )
        device = (
            self.env["device.device"]
            .create(
                {
                    "name": "HTTP permission probe",
                    "identifier": "http-permission-probe",
                    "comm_protocol": "http",
                    "endpoint": "example.invalid",
                }
            )
            .with_user(reader)
        )
        with (
            patch.object(type(device), "_require_connection") as connection,
            patch.object(type(device), "_write_state_retry") as state,
        ):
            for name in (
                "http_connect",
                "http_disconnect",
                "http_read_data",
                "https_connect",
                "https_disconnect",
                "https_read_data",
            ):
                with self.subTest(method=name), self.assertRaises(AccessError):
                    getattr(device, name)()
            connection.assert_not_called()
            state.assert_not_called()
