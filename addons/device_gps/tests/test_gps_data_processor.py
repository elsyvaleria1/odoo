from odoo.tests import tagged

from odoo.addons.device.tests.common import DeviceTransactionCase


@tagged("post_install", "-at_install")
class TestGpsFieldMapping(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.processor = cls.env["device.gps.data.processor"]

    def test_teltonika_battery_level_mapped(self):
        mapping = self.processor.get_field_mapping("teltonika")
        self.assertEqual(mapping.get("113"), "battery_level")

    def test_battery_level_stored_unscaled(self):
        log_vals = {}
        self.processor._process_field_value("battery_level", 85, log_vals)
        self.assertEqual(log_vals["battery_level"], 85)

    def test_out_of_range_timestamp_returns_none_not_raises(self):
        self.assertIsNone(
            self.processor._process_timestamp(10**19, device_type="other")
        )
        self.assertIsNone(
            self.processor._process_timestamp(10**19, device_type="teltonika")
        )

    def test_valid_timestamp_still_parses(self):
        parsed = self.processor._process_timestamp(1754740800, device_type="other")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2025)


@tagged("post_install", "-at_install")
class TestGpsFuelDelta(DeviceTransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.processor = cls.env["device.gps.data.processor"]
        cls.device = cls.env["device.device"].create(
            {
                "name": "Fuel tracker",
                "identifier": "FUEL-DELTA-1",
                "auth_type": "none",
                "comm_protocol": "https",
                "processing_mode": "sync",
                "is_gps_device": True,
                "fuel_tank_capacity": 50.0,
            }
        )

    def _previous(self, **vals):
        return self.env["device.data.log.gps"].create(
            {
                "device_id": self.device.id,
                "latitude": 19.28,
                "longitude": -99.65,
                "timestamp": "2026-09-28 10:00:00",
                **vals,
            }
        )

    def test_a_percentage_only_tracker_reports_a_refill(self):
        previous = self._previous(fuel_level=40.0)
        log_vals = {"fuel_level": 90.0, "timestamp": previous.timestamp}
        self.processor._compute_fuel_delta(log_vals, self.device, previous)
        self.assertEqual(log_vals["fuel_refilled"], 25.0)

    def test_a_percentage_only_tracker_reports_consumption(self):
        previous = self._previous(fuel_level=40.0)
        log_vals = {"fuel_level": 30.0}
        self.processor._compute_fuel_delta(log_vals, self.device, previous)
        self.assertEqual(log_vals["fuel_consumed"], 5.0)

    def test_no_level_at_all_computes_nothing(self):
        previous = self._previous()
        log_vals = {}
        self.processor._compute_fuel_delta(log_vals, self.device, previous)
        self.assertNotIn("fuel_refilled", log_vals)
        self.assertNotIn("fuel_consumed", log_vals)
