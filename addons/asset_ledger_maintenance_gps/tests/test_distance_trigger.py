from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

ACCESSOR = "_get_current_gps_odometer"


@tagged("post_install", "-at_install")
class TestKmTrigger(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Vehicle",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": True,
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.equipment = cls.env["product.trace"].create(
            {
                "name": "VEH001",
                "product_id": cls.product.id,
            }
        )
        cls.plan = cls.env["maintenance.plan"].create(
            {
                "asset_id": cls.equipment.asset_id.id,
                "distance_interval": 10000,
                "last_maintenance_odometer": 5000,
                "date_first_occurrence": fields.Datetime.now() + timedelta(days=200),
                "repeat_interval": 1,
                "repeat_unit": "year",
            }
        )

    def _read(self, odometer, field):
        with patch.object(type(self.equipment), ACCESSOR, return_value=odometer):
            self.plan.invalidate_recordset()
            return self.plan[field]

    def _state(self, odometer):
        with patch.object(type(self.equipment), ACCESSOR, return_value=odometer):
            self.plan.invalidate_recordset()
            self.plan._compute_state()
            return self.plan.state

    def test_current_odometer_reads_gps(self):
        self.assertEqual(self._read(12000.0, "current_odometer"), 12000)

    def test_distance_remaining(self):
        self.assertEqual(self._read(12000.0, "distance_remaining"), 3000)

    def test_state_overdue_when_km_reached_before_time(self):
        self.assertEqual(self._state(15500.0), "overdue")

    def test_state_follows_time_when_km_not_reached(self):
        self.assertEqual(self._state(12000.0), "upcoming")

    def test_no_gps_reading_falls_back_to_time(self):
        self.assertEqual(self._state(0.0), "upcoming")

    def test_km_disabled_ignores_odometer(self):
        self.plan.distance_interval = 0
        self.assertEqual(self._read(99999.0, "distance_remaining"), 0)
        self.assertEqual(self._state(99999.0), "upcoming")

    def _complete(self, odometer):
        with patch.object(type(self.equipment), ACCESSOR, return_value=odometer):
            self.plan.invalidate_recordset()
            self.plan._get_open_order().action_done()

    def test_completing_service_rearms_km_baseline(self):
        self.assertEqual(self._state(16000.0), "overdue")
        self._complete(16000.0)
        self.assertEqual(self.plan.last_maintenance_odometer, 16000)
        self.assertEqual(self.plan.next_maintenance_odometer, 26000)
        self.assertEqual(self._read(16000.0, "distance_remaining"), 10000)
        self.assertEqual(self._state(16000.0), "upcoming")

    def test_completion_without_gps_keeps_baseline(self):
        self._complete(0.0)
        self.assertEqual(self.plan.last_maintenance_odometer, 5000)
