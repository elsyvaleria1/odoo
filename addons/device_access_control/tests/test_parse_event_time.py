from datetime import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.device_access_control.controllers.access_device_controller import (
    AccessDeviceController,
)


@tagged("post_install", "-at_install")
class TestParseEventTime(TransactionCase):
    def test_negative_offset_converted_to_utc(self):
        result = AccessDeviceController._parse_event_time("2025-01-01T12:00:00-06:00")
        self.assertEqual(result, datetime(2025, 1, 1, 18, 0, 0))

    def test_positive_offset_converted_to_utc(self):
        result = AccessDeviceController._parse_event_time("2025-06-15T09:30:00+02:00")
        self.assertEqual(result, datetime(2025, 6, 15, 7, 30, 0))

    def test_naive_timestamp_left_as_utc(self):
        result = AccessDeviceController._parse_event_time("2025-01-01T12:00:00")
        self.assertEqual(result, datetime(2025, 1, 1, 12, 0, 0))
