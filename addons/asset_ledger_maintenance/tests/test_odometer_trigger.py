from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import archive_maintenance_approval_categories


@tagged("post_install", "-at_install")
class TestOdometerTrigger(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        archive_maintenance_approval_categories(cls.env)
        cls.product = cls.env["product.product"].create(
            {
                "name": "Odometer probe truck",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": True,
                "asset_kind_id": cls.env.ref("resource.kind_vehicle").id,
            }
        )
        cls.asset = cls.env["product.trace"].create(
            {"name": "ODO-TRIGGER-1", "product_id": cls.product.id}
        )
        # Sending an order out routes the asset through the warehouse
        # its quant sits in, so the plan is only generable once the asset is
        # actually located somewhere that allows maintenance.
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.allow_maintenance = True
        cls.env["stock.quant"]._update_available_quantity(
            cls.product, cls.warehouse.lot_stock_id, 1.0, trace_id=cls.asset
        )
        cls.asset.invalidate_recordset(["location_id"])
        cls.plan = cls.env["maintenance.plan"].create(
            {
                "asset_id": cls.asset.asset_id.id,
                "repeat_interval": 5,
                "repeat_unit": "year",
                "date_first_occurrence": fields.Datetime.now() + relativedelta(years=1),
                "distance_interval": 10000,
                "last_maintenance_odometer": 5000,
            }
        )

    def _read_odometer(self, value):
        self.env["resource.log"].create(
            {
                "asset_id": self.asset.asset_id.id,
                "date": fields.Date.today(),
                "odometer": value,
                "source": "manual",
            }
        )

    def test_the_plan_reads_the_odometer_off_the_ledger(self):
        self._read_odometer(9000)
        self.assertEqual(self.plan.current_odometer, 9000)
        self.assertEqual(self.plan.distance_remaining, 6000)

    def test_a_plan_is_not_due_before_its_threshold(self):
        self._read_odometer(9000)
        self.assertNotIn(self.plan, self.plan._get_due_plans(fields.Datetime.now()))

    def test_a_plan_past_its_threshold_is_due_though_the_date_is_years_off(self):
        self._read_odometer(15000)
        due = self.plan._get_due_plans(fields.Datetime.now())
        self.assertIn(self.plan, due)
        self.assertEqual(self.plan.state, "overdue")

    def test_the_cron_sends_the_order_out_from_distance_alone(self):
        self._read_odometer(15000)
        order = self.plan._get_open_order()
        self.assertGreater(order.date_scheduled_start, fields.Datetime.now())
        self.env["maintenance.plan"]._cron_start_due_orders()
        self.assertTrue(
            order.picking_ids,
            "a plan past its odometer threshold must send its order out",
        )
        self.assertLessEqual(order.date_scheduled_start, fields.Datetime.now())

    def test_completing_the_service_banks_the_odometer_it_was_done_at(self):
        self._read_odometer(15000)
        self.plan._get_open_order().action_done()
        self.assertEqual(self.plan.last_maintenance_odometer, 15000)
        self.assertEqual(self.plan.next_maintenance_odometer, 25000)

    def test_a_plan_without_a_distance_interval_ignores_the_odometer(self):
        self.plan.distance_interval = 0
        self._read_odometer(999999)
        self.assertFalse(self.plan._is_odometer_due())
        self.assertEqual(self.plan.distance_remaining, 0)

    def test_the_distance_unit_is_the_assets_own_and_is_not_asserted(self):
        self.assertEqual(
            self.plan.odometer_uom_name,
            self.asset.odometer_uom_name,
            "a plan reports the unit its asset keeps, not a hardcoded one",
        )
        for name in (
            "distance_interval",
            "distance_remaining",
            "current_odometer",
            "last_maintenance_odometer",
            "next_maintenance_odometer",
        ):
            with self.subTest(field=name):
                field = self.plan._fields[name]
                self.assertEqual(
                    field.type,
                    "float",
                    "an odometer is a Float on the asset; an Integer here "
                    "truncates it silently",
                )
                label = field.get_description(self.env)["string"]
                self.assertNotIn("km", label.lower())
                self.assertNotIn("km", (field.help or "").lower())

    def test_a_fractional_odometer_reading_is_not_truncated(self):
        self._read_odometer(15000.5)
        self.assertAlmostEqual(self.plan.current_odometer, 15000.5, places=2)

    def test_a_telemetry_reading_on_the_meter_makes_the_plan_due(self):
        # No ledger row: the reading lands on the asset's meter alone, as a
        # GPS feed would. The plan reads the master object, not the lot.
        self._read_odometer(6000)
        self.plan.invalidate_recordset()
        self.assertEqual(self.plan.current_odometer, 6000)
        self.assertFalse(self.plan._is_odometer_due())
        meter = self.asset.asset_id.odometer_meter_id
        self.assertTrue(meter)
        meter.record(15100, source="telemetry")
        self.plan.invalidate_recordset()
        self.assertEqual(self.plan.odometer_meter_id, meter)
        self.assertEqual(self.plan.current_odometer, 15100)
        self.assertTrue(self.plan._is_odometer_due())
        self.assertEqual(self.plan.state, "overdue")
