from datetime import datetime, timedelta

from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestValidateOdometer(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.processor = cls.env["device.gps.data.processor"]
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Odometer Test Config",
                "auth_type": "bearer",
                "auth_token": "test_token_odo",
                "reports_odometer": True,
                "odometer_correction_factor": 1.0,
            }
        )
        cls.category = cls.env["device.kind"].create(
            {
                "name": "GPS Tracker Category",
                "code": "gps_tracker",
                "comm_protocol": "http",
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Odo Tracker",
                "identifier": "ODO-001",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.50",
                "company_id": cls.company.id,
                "device_category_id": cls.category.id,
                "odometer_initial_offset": 0.0,
            }
        )
        cls.base_ts = datetime(2026, 1, 1, 8, 0, 0)

    def _make_log(self, odometer, moment, valid=True):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": moment,
                "latitude": 0.0,
                "longitude": 0.0,
                "odometer": odometer,
                "odometer_valid": valid,
            }
        )

    def test_first_reading_accepted_as_baseline(self):
        log_vals = {
            "odometer": 10000,
            "timestamp": self.base_ts,
            "device_id": self.device.id,
        }
        self.processor._check_odometer(log_vals, self.device)
        self.assertNotIn("odometer_valid", log_vals)

    def test_regression_is_flagged_invalid(self):
        self._make_log(10000, self.base_ts)
        log_vals = {
            "odometer": 9000,
            "timestamp": self.base_ts + timedelta(hours=1),
            "device_id": self.device.id,
        }
        self.processor._check_odometer(log_vals, self.device)
        self.assertIn("odometer_valid", log_vals)
        self.assertFalse(log_vals["odometer_valid"])

    def test_small_backward_jitter_within_tolerance_not_flagged(self):
        self._make_log(10000, self.base_ts)
        log_vals = {
            "odometer": 9999.5,
            "timestamp": self.base_ts + timedelta(hours=1),
            "device_id": self.device.id,
        }
        self.processor._check_odometer(log_vals, self.device)
        self.assertNotIn("odometer_valid", log_vals)

    def test_implausible_rate_is_flagged_invalid(self):
        self._make_log(10000, self.base_ts)
        log_vals = {
            "odometer": 10500,
            "timestamp": self.base_ts + timedelta(hours=1),
            "device_id": self.device.id,
        }
        self.processor._check_odometer(log_vals, self.device)
        self.assertIn("odometer_valid", log_vals)
        self.assertFalse(log_vals["odometer_valid"])

    def test_absent_odometer_is_skipped(self):
        self._make_log(10000, self.base_ts)
        log_vals = {
            "odometer": 0,
            "timestamp": self.base_ts + timedelta(hours=1),
            "device_id": self.device.id,
        }
        self.processor._check_odometer(log_vals, self.device)
        self.assertNotIn("odometer_valid", log_vals)

    def test_baseline_ignores_invalid_prior_log(self):
        self._make_log(10000, self.base_ts)
        self._make_log(99999, self.base_ts + timedelta(hours=1), valid=False)
        log_vals = {
            "odometer": 10100,
            "timestamp": self.base_ts + timedelta(hours=2),
            "device_id": self.device.id,
        }
        self.processor._check_odometer(log_vals, self.device)
        self.assertNotIn("odometer_valid", log_vals)


@tagged("post_install", "-at_install")
class TestRealOdometerWithOffset(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.config = cls.env["device.profile"].create(
            {
                "name": "Offset Test Config",
                "auth_type": "bearer",
                "auth_token": "test_token_offset",
                "reports_odometer": True,
                "odometer_correction_factor": 1.0,
            }
        )
        cls.device = cls.env["device.device"].create(
            {
                "name": "Offset Tracker",
                "identifier": "ODO-OFF-001",
                "config_id": cls.config.id,
                "comm_protocol": "http",
                "endpoint": "192.168.1.51",
                "company_id": cls.company.id,
                "odometer_initial_offset": 500.0,
            }
        )

    def _make_log(self, moment, **extra):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": moment,
                "latitude": 19.0,
                "longitude": -99.0,
                **extra,
            }
        )

    def test_missing_odometer_does_not_inherit_the_offset(self):
        ghost = self._make_log(datetime(2026, 1, 1, 8, 0, 0))
        self.assertEqual(
            ghost.real_odometer,
            0.0,
            "a payload with no odometer must not store the bare offset, or it "
            "pollutes every MIN/MAX aggregate built on NULLIF(real_odometer, 0)",
        )

    def test_genuine_reading_still_gets_the_offset(self):
        log = self._make_log(datetime(2026, 1, 1, 9, 0, 0), odometer=100.0)
        self.assertEqual(log.real_odometer, 600.0)
