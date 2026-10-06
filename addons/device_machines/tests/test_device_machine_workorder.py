from datetime import datetime

from psycopg import IntegrityError

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import DeviceMachinesCommon


@tagged("post_install", "-at_install")
class TestRemoteMachineWorkorder(DeviceMachinesCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Run = cls.env["device.machine.workorder"]
        cls.product = cls.env["product.product"].create(
            {"name": "PLC Test Product", "type": "consu", "is_storable": True}
        )
        cls.workcenter = cls.env["mrp.workcenter"].create({"name": "PLC Workcenter"})
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_id": cls.product.id,
                "product_tmpl_id": cls.product.product_tmpl_id.id,
                "product_qty": 1.0,
                "operation_ids": [
                    (0, 0, {"name": "Fill", "workcenter_id": cls.workcenter.id})
                ],
            }
        )
        production = cls.env["mrp.production"].create(
            {"product_id": cls.product.id, "product_qty": 10.0, "bom_id": cls.bom.id}
        )
        production.action_confirm()
        cls.workorder = production.workorder_ids[:1]

    def setUp(self):
        super().setUp()
        if not self.workorder:
            self.skipTest("MRP did not generate a work order in this environment")

    def _make_run(self, **vals):
        values = {
            "device_id": self.device.id,
            "workorder_id": self.workorder.id,
            "count_start": 0,
            "count_end": 0,
            "date_start": datetime(2026, 6, 18, 14, 0, 0),
        }
        values.update(vals)
        return self.Run.create(values)

    def test_accumulate_opens_run(self):
        run = self.Run._accumulate(
            self.device, self.workorder, 100, datetime(2026, 6, 18, 14, 0, 0)
        )

        self.assertEqual(run.device_id, self.device)
        self.assertEqual(run.workorder_id, self.workorder)
        self.assertEqual(run.count_start, 100)
        self.assertEqual(run.count_end, 100)
        self.assertEqual(run.date_start, datetime(2026, 6, 18, 14, 0, 0))

    def test_accumulate_updates_existing_run(self):
        self.Run._accumulate(
            self.device, self.workorder, 100, datetime(2026, 6, 18, 14, 0, 0)
        )
        run = self.Run._accumulate(
            self.device, self.workorder, 300, datetime(2026, 6, 18, 14, 30, 0)
        )

        self.assertEqual(run.count_start, 100)
        self.assertEqual(run.count_end, 300)
        self.assertEqual(run.date_end, datetime(2026, 6, 18, 14, 30, 0))
        self.assertEqual(run.bottles, 200)

    def test_bottles_clamped_on_reset(self):
        run = self._make_run(count_start=500, count_end=0)

        self.assertEqual(run.bottles, 0)

    def test_duration_and_rate(self):
        run = self._make_run(
            count_start=0,
            count_end=120,
            date_end=datetime(2026, 6, 18, 15, 0, 0),
        )

        self.assertEqual(run.bottles, 120)
        self.assertEqual(run.duration_min, 60.0)
        self.assertEqual(run.bottles_per_hour, 120.0)
        self.assertEqual(run.bottles_per_min, 2.0)

    def test_workorder_plc_rollup_fields(self):
        self._make_run(count_start=0, count_end=80)

        self.assertEqual(self.workorder.plc_run_count, 1)
        self.assertEqual(self.workorder.plc_bottle_count, 80)

    @mute_logger("odoo.db.cursor")
    def test_unique_constraint_device_workorder(self):
        self._make_run(count_end=10)
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._make_run(count_end=20, date_start=datetime(2026, 6, 18, 15, 0, 0))
            self.env.flush_all()

    def test_dashboard_data_shape(self):
        self._make_run(count_start=0, count_end=90)

        data = self.Run.get_dashboard_data(self.workorder.id)

        self.assertEqual(data["totals"]["bottles"], 90)
        self.assertEqual(data["totals"]["runs"], 1)
        self.assertIn("chart", data)
