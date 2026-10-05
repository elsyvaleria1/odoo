from datetime import timedelta

from odoo import fields
from odoo.tests import tagged

from .test_product_trace import StockLotGpsTestBase


@tagged("post_install", "-at_install")
class TestGetCurrentGpsOdometer(StockLotGpsTestBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config.write(
            {
                "reports_odometer": True,
                "odometer_correction_factor": 1.0,
            }
        )
        cls.device.odometer_initial_offset = 0.0
        cls.GpsLog = cls.env["device.data.log.gps"]

    def _log(self, odometer, days_ago, valid=True):
        return self.GpsLog.create(
            {
                "device_id": self.device.id,
                "timestamp": fields.Datetime.now() - timedelta(days=days_ago),
                "latitude": 0.0,
                "longitude": 0.0,
                "odometer": odometer,
                "odometer_valid": valid,
            }
        )

    def test_no_device_returns_zero(self):
        lot = self.env["product.trace"].create(
            {
                "name": "NO-GPS",
                "product_id": self.product.id,
                "company_id": self.company.id,
                "odometer_uom_id": self.km_uom.id,
            }
        )
        self.assertEqual(lot._get_current_gps_odometer(), 0.0)

    def test_returns_the_latest_valid_reading_not_the_highest(self):
        self._log(10200, days_ago=5)
        self._log(10000, days_ago=2)
        self.assertEqual(self.vehicle._get_current_gps_odometer(), 10000)

    def test_ignores_invalid_readings(self):
        self._log(10000, days_ago=3)
        self._log(99999, days_ago=1, valid=False)
        self.assertEqual(self.vehicle._get_current_gps_odometer(), 10000)

    def test_falls_back_to_last_known_when_window_empty(self):
        self._log(10500, days_ago=60)
        self.assertEqual(self.vehicle._get_current_gps_odometer(), 10500)

    def test_fallback_prefers_latest_not_max(self):
        self._log(999999, days_ago=90)
        self._log(10500, days_ago=60)
        self.assertEqual(self.vehicle._get_current_gps_odometer(), 10500)

    def test_window_excludes_old_spike(self):
        self._log(999999, days_ago=60)
        self._log(10000, days_ago=5)
        self.assertEqual(self.vehicle._get_current_gps_odometer(), 10000)

    def test_a_junk_window_falls_back_to_the_default(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "asset_gps.odometer_lookback_days", "thirty"
        )

        self.assertEqual(
            self.env["resource.asset"]._gps_odometer_lookback_days(),
            30,
            "A parameter that will not parse must not raise.",
        )

    def test_a_non_positive_window_falls_back_to_the_default(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "asset_gps.odometer_lookback_days", "-5"
        )

        self.assertEqual(self.env["resource.asset"]._gps_odometer_lookback_days(), 30)

    def test_a_junk_window_does_not_abort_the_cron(self):
        self._log(10000, days_ago=5)
        self.env["ir.config_parameter"].sudo().set_param(
            "asset_gps.odometer_lookback_days", "thirty"
        )

        self.env["product.trace"]._cron_record_gps_odometer()

        self.assertTrue(
            self.env["resource.log"].search(
                [("trace_id", "=", self.vehicle.id), ("source", "=", "gps")]
            ),
            "One bad parameter used to abort the run for every asset.",
        )
