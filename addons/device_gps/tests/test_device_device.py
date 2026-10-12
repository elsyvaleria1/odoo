from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestRemoteDeviceGps(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.config = cls.env["device.profile"].create(
            {
                "name": "GPS Test Config",
                "auth_type": "bearer",
                "auth_token": "test_token_gps",
            }
        )
        cls.gps_category = cls.env["device.kind"].create(
            {
                "name": "GPS Tracker Category",
                "code": "gps_tracker",
                "comm_protocol": "http",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "GPS Tracker 001",
                "identifier": "GPS-001-SERIAL",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.100",
                "company_id": cls.company.id,
                "device_category_id": cls.gps_category.id,
            }
        )

    def test_create_device_device_uses_identifier(self):
        self.assertEqual(self.device.identifier, "GPS-001-SERIAL")
        self.assertFalse(
            hasattr(self.device, "device_serial"),
            "device_serial was renamed to identifier",
        )

    def test_is_gps_device_true_when_category_code_matches(self):
        self.assertTrue(self.device.is_gps_device)

    def test_an_imei_alone_no_longer_makes_a_device_a_gps_device(self):
        category = self.env["device.kind"].create(
            {"name": "Cellular Terminal", "code": "cellular_terminal"}
        )
        device = self.env["device.device"].create(
            {
                "name": "Terminal With A SIM",
                "identifier": "SIM-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.201",
                "company_id": self.company.id,
                "device_category_id": category.id,
                "imei": "356938035643809",
            }
        )
        self.assertFalse(device.is_gps_device)

    def test_gps_declares_its_own_category(self):
        self.assertIn(
            "gps_tracker",
            self.env["device.device"]._device_kind_categories("gps"),
        )

    def test_is_gps_device_false_without_gps_category(self):
        other_category = self.env["device.kind"].create(
            {
                "name": "Generic Sensor",
                "code": "sensor",
                "comm_protocol": "http",
            }
        )
        device = self.env["device.device"].create(
            {
                "name": "Generic Device",
                "identifier": "SENSOR-001",
                "config_id": self.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.200",
                "company_id": self.company.id,
                "device_category_id": other_category.id,
            }
        )
        self.assertFalse(device.is_gps_device)

    def test_log_gps_count_starts_at_zero(self):
        self.assertEqual(self.device.log_gps_count, 0)

    def test_log_gps_ids_relation_exists(self):
        self.assertEqual(self.device.log_gps_ids._name, "device.data.log.gps")

    def test_action_view_logs_gps_returns_correct_model(self):
        action = self.device.action_view_logs_gps()
        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "device.data.log.gps")


@tagged("post_install", "-at_install")
class TestRemoteDataLogGps(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.DataLog = cls.env["device.data.log.gps"]

    def test_gps_log_model_is_registered(self):
        self.assertIn("device.data.log.gps", self.env)

    def test_gps_log_model_has_expected_fields(self):
        fields_info = self.DataLog._fields
        for field_name in ("device_id", "timestamp", "latitude", "longitude", "speed"):
            self.assertIn(field_name, fields_info, f"Missing field: {field_name}")

    def test_a_fix_is_named_by_its_device_and_the_reader_s_local_time(self):
        device = self.env["device.device"].create(
            {"name": "Truck 14", "identifier": "GPS-NAME-014"}
        )
        fix = self.DataLog.create(
            {
                "device_id": device.id,
                "timestamp": "2026-09-27 10:47:12",
                "latitude": 25.1,
                "longitude": -107.65,
            }
        )
        self.assertEqual(
            fix.with_context(tz="America/Mazatlan").display_name,
            "Truck 14 · 2026-09-27 03:47:12",
        )
        self.assertEqual(
            fix.with_context(tz="UTC").display_name, "Truck 14 · 2026-09-27 10:47:12"
        )


@tagged("post_install", "-at_install")
class TestGpsLogCountWindow(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.window_config = cls.env["device.profile"].create(
            {"name": "GPS Count Window Config"}
        )
        cls.window_device = cls.env["device.device"].create(
            {
                "name": "Counting Tracker",
                "identifier": "GPS-COUNT-WINDOW",
                "config_id": cls.window_config.id,
                "comm_protocol": "http",
                "endpoint": "10.0.0.9",
            }
        )

    def _point_at(self, days_ago):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.window_device.id,
                "timestamp": fields.Datetime.now() - timedelta(days=days_ago),
                "latitude": 19.4,
                "longitude": -99.1,
            }
        )

    def test_history_outside_the_window_is_not_counted(self):
        for days in (0, 0, 0, 30, 400):
            self._point_at(days)
        self.window_device.invalidate_recordset()
        self.assertEqual(
            self.window_device.log_gps_count,
            3,
            "log_gps_count is aggregating the whole tracking history again",
        )

    def test_a_silent_tracker_counts_zero(self):
        self._point_at(30)
        self.window_device.invalidate_recordset()
        self.assertEqual(self.window_device.log_gps_count, 0)


@tagged("post_install", "-at_install")
class TestGpsTrackingToggle(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env["device.profile"].create(
            {"name": "Toggle Config", "gps_tracking_enabled": True}
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Toggle Tracker",
                "identifier": "TOGGLE-001",
                "config_id": cls.config.id,
                "comm_protocol": "http",
            }
        )

    def test_config_toggle_leaves_existing_devices_alone(self):
        self.assertTrue(self.device.gps_tracking_enabled)
        self.config.gps_tracking_enabled = False
        self.env.flush_all()
        self.env.invalidate_all()
        self.assertTrue(
            self.device.gps_tracking_enabled,
            "the config value is only the default for a new assignment; "
            "a device-level override must survive edits of the config",
        )

    def test_new_device_takes_the_config_default(self):
        disabled = self.env["device.profile"].create(
            {"name": "Toggle Config Off", "gps_tracking_enabled": False}
        )
        device = self.env["device.device"].create(
            {
                "name": "Toggle Tracker Off",
                "identifier": "TOGGLE-002",
                "config_id": disabled.id,
                "comm_protocol": "http",
            }
        )
        self.assertFalse(device.gps_tracking_enabled)


@tagged("post_install", "-at_install")
class TestDeviceWithHistoryIsNotDeletable(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(name="Delete Guard Config")
        cls.device = cls._create_device_device(
            config=cls.config, identifier="DELETE-GUARD-1"
        )

    def _point(self, device):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": device.id,
                "timestamp": fields.Datetime.now(),
                "latitude": 19.4,
                "longitude": -99.1,
            }
        )

    def test_a_device_without_history_is_deletable(self):
        spare = self._create_device_device(
            config=self.config, identifier="DELETE-GUARD-2"
        )
        spare.unlink()
        self.assertFalse(spare.exists())

    def test_a_device_with_history_refuses_to_be_deleted(self):
        self._point(self.device)
        with self.assertRaises(UserError):
            self.device.unlink()
        self.assertTrue(self.device.exists())

    def test_the_message_names_the_device(self):
        self._point(self.device)
        with self.assertRaises(UserError) as caught:
            self.device.unlink()
        self.assertIn(self.device.display_name, str(caught.exception))
