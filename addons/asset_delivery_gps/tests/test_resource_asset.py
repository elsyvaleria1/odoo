from datetime import timedelta

from odoo.exceptions import UserError

from .common import GpsBridgeCase


class TestResourceAssetGpsAccessors(GpsBridgeCase):
    def test_reading_comes_from_the_gps_log(self):
        log = self.gps_log(15000.0, fuel_level=72.5)
        self.device.log_gps_last_id = log

        self.assertEqual(self.asset.get_current_odometer(), 15000.0)
        self.assertEqual(self.asset.get_current_fuel_percentage(), 72.5)

    def test_reading_flagged_invalid_is_not_published(self):
        self.gps_log(10000.0, minutes_ago=30)
        spike = self.gps_log(99999.0, minutes_ago=10, valid=False)
        self.device.log_gps_last_id = spike

        self.assertEqual(self.asset.get_current_odometer(), 10000.0)

    def test_no_valid_reading_asks_for_manual_entry(self):
        self.device.log_gps_last_id = self.gps_log(99999.0, valid=False)

        with self.assertRaises(UserError):
            self.asset.get_current_odometer()

    def test_no_device_asks_for_manual_entry(self):
        self.asset.gps_device_id = False

        with self.assertRaises(UserError):
            self.asset.get_current_odometer()
        with self.assertRaises(UserError):
            self.asset.get_current_fuel_percentage()

    def test_no_data_yet_asks_for_manual_entry(self):
        self.device.log_gps_last_id = False

        with self.assertRaises(UserError):
            self.asset.get_current_odometer()
        with self.assertRaises(UserError):
            self.asset.get_current_fuel_percentage()


class TestResourceAssetGpsFreshness(GpsBridgeCase):
    def test_a_stale_reading_is_not_served_as_current(self):
        self.device.log_gps_last_id = self.gps_log(11111.0, days_ago=90)

        with self.assertRaises(UserError):
            self.asset.get_current_fuel_percentage()
        with self.assertRaises(UserError):
            self.asset.get_current_odometer()

    def test_a_recent_reading_is_still_served(self):
        self.device.log_gps_last_id = self.gps_log(
            12000.0, minutes_ago=30, fuel_level=61.0
        )

        self.assertEqual(self.asset.get_current_fuel_percentage(), 61.0)
        self.assertEqual(self.asset.get_current_odometer(), 12000.0)

    def test_the_window_is_the_shared_config_parameter(self):
        self.device.log_gps_last_id = self.gps_log(
            13000.0, days_ago=45, fuel_level=42.0
        )

        with self.assertRaises(UserError):
            self.asset.get_current_fuel_percentage()

        self.env["ir.config_parameter"].sudo().set_param(
            "asset_gps.odometer_lookback_days", "60"
        )

        self.assertEqual(self.asset.get_current_fuel_percentage(), 42.0)

    def test_an_unparsable_window_falls_back_to_the_default(self):
        self.device.log_gps_last_id = self.gps_log(
            14000.0, minutes_ago=30, fuel_level=55.0
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "asset_gps.odometer_lookback_days", "30 days"
        )

        self.assertEqual(self.asset.get_current_odometer(), 14000.0)
        self.assertEqual(self.asset.get_current_fuel_percentage(), 55.0)

    def test_a_valid_reading_outside_the_window_is_not_served(self):
        self.gps_log(10000.0, days_ago=200)
        self.device.log_gps_last_id = self.gps_log(99999.0, valid=False)

        with self.assertRaises(UserError):
            self.asset.get_current_odometer()


class TestResourceAssetTripReadingAge(GpsBridgeCase):
    """A trip takes an odometer from the last two hours, not the last 30 days."""

    def test_an_odometer_older_than_two_hours_is_not_a_trip_reading(self):
        self.device.log_gps_last_id = self.gps_log(
            12000.0, minutes_ago=150, fuel_level=61.0
        )

        with self.assertRaisesRegex(UserError, "last 120 minutes"):
            self.asset.get_current_odometer()
        self.assertEqual(
            self.asset.get_current_fuel_percentage(),
            61.0,
            "The fuel level keeps the day window of the lookback parameter.",
        )

    def test_the_trip_reading_age_is_a_system_parameter(self):
        self.gps_log(12000.0, minutes_ago=150)
        self.env["ir.config_parameter"].sudo().set_param(
            "asset_delivery_gps.trip_reading_max_age_minutes", "180"
        )

        self.assertEqual(self.asset.get_current_odometer(), 12000.0)

    def test_an_unparsable_trip_reading_age_falls_back_to_two_hours(self):
        self.gps_log(12000.0, minutes_ago=90)
        self.env["ir.config_parameter"].sudo().set_param(
            "asset_delivery_gps.trip_reading_max_age_minutes", "two hours"
        )

        self.assertEqual(self.asset.get_current_odometer(), 12000.0)
        self.assertEqual(
            self.env["resource.resource"]._trip_reading_max_age(), timedelta(hours=2)
        )

    def test_the_latest_reading_is_taken_not_the_highest(self):
        self.gps_log(12500.0, minutes_ago=60)
        self.gps_log(12000.0, minutes_ago=5)

        self.assertEqual(self.asset.get_current_odometer(), 12000.0)
