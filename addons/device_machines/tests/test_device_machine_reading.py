from datetime import UTC, datetime

from odoo.tests import tagged

from ..models.device_machine_reading import MONITOR_KEEP
from .common import DeviceMachinesCommon


@tagged("post_install", "-at_install")
class TestRemoteMachineReading(DeviceMachinesCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Reading = cls.env["device.machine.reading"]

    def test_record_creates_reading_naive_utc(self):
        reading = self.Reading._record(
            self.device, datetime(2026, 6, 18, 14, 0, 5, tzinfo=UTC), 42
        )

        self.assertEqual(reading.device_id, self.device)
        self.assertEqual(reading.count, 42)
        self.assertEqual(reading.timestamp, datetime(2026, 6, 18, 14, 0, 5))

    def test_buffer_trims_to_monitor_keep(self):
        for i in range(MONITOR_KEEP + 5):
            self.Reading._record(
                self.device, datetime(2026, 6, 18, 14, 0, i, tzinfo=UTC), i
            )

        kept = self.Reading.search([("device_id", "=", self.device.id)])
        self.assertEqual(len(kept), MONITOR_KEEP)
        self.assertEqual(max(kept.mapped("count")), MONITOR_KEEP + 4)
