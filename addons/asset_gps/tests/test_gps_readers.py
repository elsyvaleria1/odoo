from datetime import datetime, timedelta

from odoo import Command, fields
from odoo.tests import tagged

from .test_product_trace import StockLotGpsTestBase


@tagged("post_install", "-at_install")
class TestGpsReaders(StockLotGpsTestBase):
    """The one reader of a vehicle's odometer at a moment and of its position."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config.write({"reports_odometer": True, "odometer_correction_factor": 1.0})
        cls.device.odometer_initial_offset = 0.0
        cls.asset = cls.vehicle.asset_id
        cls.t0 = fields.Datetime.to_datetime("2026-09-28 08:00:00")

    def _log(self, minutes, odometer=0.0, latitude=19.26, longitude=-99.6):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "timestamp": self.t0 + timedelta(minutes=minutes),
                "latitude": latitude,
                "longitude": longitude,
                "odometer": odometer,
                "odometer_valid": bool(odometer),
            }
        )

    def test_the_odometer_at_a_moment_is_the_closest_valid_reading(self):
        self._log(-20, 1000.0)
        self._log(5, 1003.0)
        self._log(1, 0.0)
        at = self.t0
        self.assertEqual(self.asset._gps_odometer_at(at), 1003.0)
        self.assertEqual(
            self.asset._gps_odometer_at(at + timedelta(hours=2)),
            0.0,
            "A reading far from the moment does not say where the vehicle was.",
        )

    def test_the_position_is_the_last_reading_at_the_moment_within_its_age(self):
        self._log(0, latitude=19.30)
        self._log(10, latitude=0.0, longitude=0.0)
        at = self.t0 + timedelta(minutes=15)
        self.assertEqual(self.asset._gps_position(at).latitude, 19.30)
        self.assertFalse(self.asset._gps_position(at, max_age=timedelta(minutes=5)))
        self.assertFalse(self.asset._gps_position(self.t0 - timedelta(minutes=1)))

    def test_the_reading_at_a_moment_takes_the_closest_and_the_earlier_on_a_tie(self):
        self._log(-10, 1000.0)
        self._log(10, 1004.0)
        self._log(25, 1006.0)
        window = timedelta(minutes=30)
        reading = self.asset._gps_odometer_reading(self.t0, before=window, after=window)
        self.assertEqual(reading.value, 1000.0)
        self.assertEqual(reading.timestamp, self.t0 - timedelta(minutes=10))
        later = self.t0 + timedelta(minutes=20)
        self.assertEqual(
            self.asset._gps_odometer_reading(later, before=window, after=window).value,
            1006.0,
        )

    def test_the_reading_as_of_a_moment_never_looks_ahead(self):
        self._log(-90, 1000.0)
        self._log(5, 1003.0)
        self.assertEqual(self.asset._gps_odometer_reading(self.t0).value, 1000.0)
        self.assertIsNone(
            self.asset._gps_odometer_reading(self.t0, before=timedelta(hours=1)),
            "A vehicle silent longer than the age allowed has no reading.",
        )

    def test_no_device_or_no_valid_reading_is_no_reading(self):
        self._log(-5, 0.0)
        self.assertIsNone(self.asset._gps_odometer_reading(self.t0))
        self.asset.gps_device_id = False
        self.assertIsNone(self.asset._gps_odometer_reading(self.t0))

    def test_the_reading_is_the_corrected_odometer(self):
        self.device.odometer_initial_offset = 250.0
        self._log(-5, 1000.0)
        self.assertEqual(self.asset._gps_odometer_reading(self.t0).value, 1250.0)

    def test_a_user_who_cannot_read_gps_logs_still_gets_the_reading(self):
        clerk = self.env["res.users"].create(
            {
                "name": "Stock Clerk",
                "login": "gps_reader_clerk",
                "group_ids": [
                    Command.set(
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("stock.group_stock_user").id,
                        ]
                    )
                ],
            }
        )
        self.assertFalse(
            self.env["device.data.log.gps"].with_user(clerk).has_access("read")
        )
        self._log(-5, 1000.0)
        reading = self.asset.with_user(clerk)._gps_odometer_reading(self.t0)
        self.assertEqual(reading.value, 1000.0)
        self.assertIsInstance(reading.timestamp, datetime)
