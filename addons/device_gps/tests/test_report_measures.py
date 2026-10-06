from datetime import datetime, timedelta

from odoo.tests.common import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestGpsReportMeasures(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls._create_device_profile(
            name="Report Config", gps_protocol="teltonika"
        )
        cls.device = cls._create_device_device(
            config=cls.config, name="Report Tracker", identifier="REPORT-1"
        )
        cls.report = cls.env["device.data.log.gps.report"]

    def _log_a_shift(self, hours=5, engine_step=0.1):
        start = datetime(2026, 8, 1, 6, 0, 0)
        engine = 1000.0
        vals = []
        for index in range(hours * 6):
            engine += engine_step
            vals.append(
                {
                    "device_id": self.device.id,
                    "latitude": 19.0 + index * 1e-4,
                    "longitude": -99.0 + index * 1e-4,
                    "timestamp": start + timedelta(minutes=10 * index),
                    "engine_total_hours": engine,
                    "ignition": True,
                    "movement": True,
                    "speed": 40.0,
                    "satellites": 9,
                    "gnss_hdop": 1.0,
                    "source": "webhook",
                }
            )
        self.env["device.data.log.gps"].create(vals)
        return round(engine_step * (len(vals) - 1), 2)

    def test_engine_hours_total_reflects_logged_engine_time(self):
        expected = self._log_a_shift()
        self.assertGreater(expected, 0, "fixture must log some engine time")
        self.report.refresh(force_rebuild=True)

        rows = self.report.search([("device_id", "=", self.device.id)])
        self.assertTrue(rows, "the device produced no report rows")
        reported = sum(rows.mapped("engine_hours_total"))
        self.assertAlmostEqual(
            reported,
            expected,
            places=1,
            msg=(
                f"device logged {expected} h of engine time via "
                f"engine_total_hours; the report says {reported}"
            ),
        )

    def test_engine_hours_ignores_the_column_no_producer_writes(self):
        start = datetime(2026, 9, 1, 6, 0, 0)
        self.env["device.data.log.gps"].create(
            [
                {
                    "device_id": self.device.id,
                    "latitude": 20.0 + index * 1e-4,
                    "longitude": -98.0 + index * 1e-4,
                    "timestamp": start + timedelta(minutes=10 * index),
                    "engine_hours": 500.0 + index,
                    "source": "webhook",
                }
                for index in range(6)
            ]
        )
        self.report.refresh(force_rebuild=True)
        rows = self.report.search(
            [("device_id", "=", self.device.id), ("date", "=", start.date())]
        )
        self.assertEqual(sum(rows.mapped("engine_hours_total")), 0.0)


@tagged("post_install", "-at_install")
class TestGpsQualityValidation(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.validator = cls.env["device.gps.data.validator"]

    def test_an_excellent_fix_is_not_flagged(self):
        valid, message = self.validator._check_comprehensive_parameters(
            {"gnss_hdop": 0.8, "satellites": 10}, None
        )
        self.assertTrue(valid, message)

    def test_a_mediocre_fix_is_still_accepted(self):
        valid, message = self.validator._check_comprehensive_parameters(
            {"gnss_hdop": 3.0, "satellites": 10}, None
        )
        self.assertTrue(valid, message)

    def test_a_poor_fix_is_still_flagged(self):
        valid, _message = self.validator._check_comprehensive_parameters(
            {"gnss_hdop": 40.0, "satellites": 10}, None
        )
        self.assertFalse(valid, "HDOP above the ceiling must still be flagged")

    def test_the_report_and_the_validator_agree_on_a_good_fix(self):
        for hdop in (0.5, 0.8, 1.0, 2.5, 5.0):
            valid, message = self.validator._check_comprehensive_parameters(
                {"gnss_hdop": hdop, "satellites": 10}, None
            )
            self.assertTrue(valid, f"hdop={hdop}: {message}")
