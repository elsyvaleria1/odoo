from datetime import datetime, timedelta

from freezegun import freeze_time
from psycopg import IntegrityError

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import Form
from odoo.tests.common import TransactionCase, mute_logger


class TestMaintenancePlan(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.MaintenancePlan = cls.env["maintenance.plan"]
        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductProduct = cls.env["product.product"]
        cls.product = cls.ProductProduct.create(
            {
                "name": "Test Equipment",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": True,
                "asset_kind_id": cls.env.ref("resource_asset.kind_equipment").id,
            }
        )
        cls.equipment = cls.ProductTrace.create(
            {"name": "EQUIP001", "product_id": cls.product.id}
        )

    def _plan(self, **vals):
        return self.MaintenancePlan.create(
            {
                "asset_id": self.equipment.asset_id.id,
                "repeat_interval": 1,
                "repeat_unit": "month",
                "date_first_occurrence": datetime.now() + timedelta(days=15),
                **vals,
            }
        )

    def test_create_maintenance_plan(self):
        plan = self._plan(repeat_interval=3)
        self.assertEqual(plan.trace_id, self.equipment)
        self.assertEqual(plan.repeat_anchor, "completion")
        self.assertIn(self.equipment.asset_id.name, plan.name)
        self.assertRecordValues(
            plan.order_ids,
            [
                {
                    "resource_ids": self.equipment.asset_id.ids,
                    "maintenance_type": "preventive",
                }
            ],
        )

    def test_next_maintenance_odometer_computed(self):
        plan = self._plan(distance_interval=10000, last_maintenance_odometer=5000)
        self.assertEqual(plan.next_maintenance_odometer, 15000)

    def test_next_maintenance_odometer_disabled_without_interval(self):
        plan = self._plan(last_maintenance_odometer=5000)
        self.assertEqual(plan.next_maintenance_odometer, 0)

    def test_cron_recompute_state_refreshes_stale(self):
        plan = self._plan()
        self.assertEqual(plan.state, "upcoming")
        with freeze_time(datetime.now() + timedelta(days=20)):
            self.MaintenancePlan._cron_recompute_state()
            plan.invalidate_recordset(["state"])
            self.assertEqual(plan.state, "overdue")

    def test_interval_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._plan(repeat_interval=0)

    def test_equipment_must_have_maintenance_ok(self):
        product = self.ProductProduct.create(
            {
                "name": "Regular Product",
                "is_storable": True,
                "tracking": "serial",
                "maintenance_ok": False,
                "asset_kind_id": self.env.ref("resource_asset.kind_equipment").id,
            }
        )
        lot = self.ProductTrace.create({"name": "REGULAR001", "product_id": product.id})
        with self.assertRaises(ValidationError) as cm:
            self._plan(asset_id=lot.asset_id.id)
        self.assertIn("recurring maintenance enabled", str(cm.exception))

    def test_a_completion_plan_counts_from_the_day_the_service_came_back(self):
        plan = self._plan(date_first_occurrence=datetime(2026, 1, 10, 14)).with_context(
            tz="UTC"
        )
        with freeze_time("2026-02-25 09:00:00"):
            plan._get_open_order().action_done()
            self.env.flush_all()
        self.assertEqual(
            plan._get_open_order().date_scheduled_start, datetime(2026, 3, 25, 14)
        )

    def test_an_archived_plan_stops_opening_orders(self):
        plan = self._plan()
        plan.action_archive()
        plan.order_ids.action_done()
        self.assertFalse(plan._get_open_order())

    @mute_logger("odoo.db.cursor")
    def test_unique_active_plan_constraint(self):
        self._plan(repeat_interval=3)
        with self.assertRaises(IntegrityError), self.env.cr.savepoint():
            self._plan(repeat_interval=3)

    def test_multiple_plans_different_intervals_allowed(self):
        monthly_plan = self._plan()
        yearly_plan = self._plan(repeat_unit="year")
        self.assertNotEqual(monthly_plan, yearly_plan)
        self.assertTrue(monthly_plan.active and yearly_plan.active)

    def test_plan_state_computation(self):
        overdue_plan = self._plan(
            date_first_occurrence=datetime.now() - timedelta(days=5)
        )
        self.assertEqual(overdue_plan.state, "overdue")
        other = self.ProductTrace.create(
            {"name": "EQUIP002", "product_id": self.product.id}
        )
        upcoming_plan = self._plan(asset_id=other.asset_id.id)
        self.assertEqual(upcoming_plan.state, "upcoming")

    def test_a_template_opens_its_plans_one_interval_out(self):
        template = self.env["maintenance.plan.template"].create(
            {
                "name": "Quarterly",
                "repeat_interval": 3,
                "repeat_unit": "month",
                "product_id": self.product.id,
                "instructions": "<p>Grease the bearings</p>",
            }
        )
        plan = template.create_plans_for_equipment(self.equipment.ids)
        self.assertRecordValues(
            plan, [{"repeat_anchor": "completion", "template_id": template.id}]
        )
        self.assertIn("Grease the bearings", plan.description)
        self.assertGreater(
            plan.date_first_occurrence, fields.Datetime.now() + timedelta(days=80)
        )

    def test_a_plan_given_no_start_falls_due_one_interval_out(self):
        with freeze_time("2026-04-10 09:00:00"):
            plan = self.MaintenancePlan.create(
                {
                    "asset_id": self.equipment.asset_id.id,
                    "repeat_interval": 2,
                    "repeat_unit": "week",
                }
            )
            self.assertEqual(plan.date_first_occurrence, datetime(2026, 4, 24, 9))
            self.assertEqual(plan.state, "upcoming")

    def test_plans_due_the_same_local_day_conflict(self):
        other = self.ProductTrace.create(
            {"name": "EQUIP003", "product_id": self.product.id}
        )
        evening = self._plan(
            tz="America/Mexico_City", date_first_occurrence=datetime(2027, 5, 11, 2)
        )
        morning = self._plan(
            asset_id=other.asset_id.id,
            tz="America/Mexico_City",
            date_first_occurrence=datetime(2027, 5, 10, 16),
        )
        self.assertEqual(evening.conflicting_plan_ids, morning)
        self.assertEqual(morning.conflicting_plan_ids, evening)

    def test_a_distance_plan_maintains_one_asset(self):
        other = self.env["product.trace"].create(
            {"name": "PLAN-DISTANCE-2", "product_id": self.equipment.product_id.id}
        )
        plan = self._plan()
        self.assertEqual(plan.resource_ids, self.equipment.asset_id)
        with self.assertRaises(ValidationError):
            plan.write(
                {
                    "distance_interval": 1000,
                    "resource_ids": [Command.link(other.asset_id.id)],
                }
            )

    def test_a_plan_without_an_asset_is_a_core_plan(self):
        plan = self.MaintenancePlan.create(
            {
                "name": "Compressor check",
                "repeat_interval": 1,
                "repeat_unit": "month",
            }
        )
        self.assertFalse(plan.asset_id)
        self.assertTrue(plan.order_ids)

    def test_generic_plan_keeps_fixed_dates_and_blocks_resources(self):
        with freeze_time("2026-01-31 09:00:00"):
            plan = self.MaintenancePlan.create({"name": "Generic plan"})
            self.assertEqual(plan.repeat_anchor, "fixed")
            self.assertTrue(plan.block_resource)
            self.assertEqual(plan.date_first_occurrence, datetime(2026, 1, 31, 9))
            self.assertEqual(plan.order_ids.name, "Generic plan")

    def test_explicit_asset_plan_defaults_remain_overridable(self):
        plan = self._plan(repeat_anchor="fixed", block_resource=True, duration=3)
        self.assertEqual(plan.repeat_anchor, "fixed")
        self.assertTrue(plan.block_resource)
        self.assertEqual(plan.duration, 3)

    def test_asset_context_supplies_scoped_ui_defaults(self):
        Plan = self.MaintenancePlan.with_context(
            default_asset_id=self.equipment.asset_id.id
        )
        defaults = Plan.default_get(["repeat_anchor", "block_resource"])
        self.assertEqual(
            defaults, {"repeat_anchor": "completion", "block_resource": False}
        )
        defaults = Plan.with_context(
            default_repeat_anchor="fixed", default_block_resource=True
        ).default_get(["repeat_anchor", "block_resource"])
        self.assertEqual(defaults, {"repeat_anchor": "fixed", "block_resource": True})

    def test_generic_plan_form_does_not_require_an_asset(self):
        with Form(self.MaintenancePlan) as form:
            form.name = "Generic plan from form"
        self.assertFalse(form.record.asset_id)
        self.assertEqual(form.record.repeat_anchor, "fixed")
        self.assertTrue(form.record.block_resource)

    def test_asset_context_start_matches_the_creation_cadence(self):
        with freeze_time("2026-04-10 09:00:00"):
            Plan = self.MaintenancePlan.with_context(
                default_asset_id=self.equipment.asset_id.id,
                default_repeat_interval=2,
                default_repeat_unit="week",
            )
            defaults = Plan.default_get(["date_first_occurrence"])
            self.assertEqual(
                defaults["date_first_occurrence"], datetime(2026, 4, 24, 9)
            )
