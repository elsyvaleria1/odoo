from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import ensure_publish_date_field


@tagged("post_install", "-at_install")
class TestProductAssetLog(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        has_publish_date = ensure_publish_date_field(cls.env)

        cls.ProductAssetLog = cls.env["resource.log"]
        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductTemplate = cls.env["product.template"]
        cls.ProductProduct = cls.env["product.product"]
        cls.Partner = cls.env["res.partner"]

        vals = {
            "name": "Test Vehicle",
            "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            "type": "consu",
            "is_storable": True,
            "tracking": "serial",
        }
        if has_publish_date:
            vals["publish_date"] = fields.Datetime.now()
        cls.vehicle_template = cls.ProductTemplate.create(vals)
        cls.vehicle_product = cls.vehicle_template.product_variant_id

        cls.asset = cls.ProductTrace.create(
            {
                "name": "TEST-ASSET-001",
                "product_id": cls.vehicle_product.id,
                "license_plate": "LOG-TEST",
                "company_id": cls.env.company.id,
            }
        )

        cls.vendor = cls.Partner.create(
            {
                "name": "Test Vendor",
                "is_company": True,
            }
        )

        cls.fuel_category = cls.env.ref("asset_ledger.product_category_fuel")
        cls.service_category = cls.env.ref(
            "asset_ledger.product_category_maintenance_and_repairs"
        )
        cls.fuel_product = cls.ProductProduct.create(
            {
                "name": "Diesel Fuel",
                "type": "service",
                "categ_id": cls.fuel_category.id,
            }
        )
        cls.maintenance_product = cls.ProductProduct.create(
            {
                "name": "Oil Change Service",
                "type": "service",
                "categ_id": cls.service_category.id,
            }
        )
        cls.insurance_product = cls.ProductProduct.create(
            {
                "name": "Vehicle Insurance",
                "type": "service",
                "categ_id": cls.service_category.id,
            }
        )

    def test_create_log_basic(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )

        self.assertEqual(log.asset_id, self.asset.asset_id)
        self.assertEqual(log.trace_id, self.asset)
        self.assertEqual(log.product_id, self.fuel_product)
        self.assertEqual(log.state, "new")
        self.assertTrue(log.active)

    def test_create_log_with_vendor(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "vendor_id": self.vendor.id,
            }
        )

        self.assertEqual(log.vendor_id, self.vendor)

    def test_create_log_with_cost(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "amount": 750.50,
            }
        )

        self.assertEqual(log.amount, 750.50)
        self.assertEqual(log.currency_id, self.env.company.currency_id)

    def test_create_fuel_log_with_quantity(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "amount": 800.0,
                "qty_fuel": 50.0,
                "odometer": 10000.0,
            }
        )

        self.assertEqual(log.qty_fuel, 50.0)
        self.assertEqual(log.odometer, 10000.0)
        self.assertEqual(log.efficiency, 0.0)

    def test_default_date(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )

        self.assertEqual(log.date, fields.Date.context_today(self.env["resource.log"]))

    def test_default_date_start(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.insurance_product.id,
            }
        )

        self.assertEqual(
            log.date_start,
            fields.Date.context_today(self.env["resource.log"]),
        )

    def test_compute_days_left_future(self):
        future_date = fields.Date.today() + timedelta(days=30)

        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.insurance_product.id,
                "date_end": future_date,
            }
        )

        self.assertGreater(log.days_left, 25)
        self.assertLess(log.days_left, 35)

    def test_compute_days_left_past(self):
        past_date = fields.Date.context_today(self.ProductAssetLog) - timedelta(days=10)

        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.insurance_product.id,
                "date_end": past_date,
            }
        )

        self.assertEqual(log.days_left, -10)

    def test_compute_days_left_no_end_date(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.insurance_product.id,
                "date_end": False,
            }
        )

        self.assertEqual(log.days_left, 0)

    def test_action_archive(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )

        self.assertTrue(log.active)

        log.action_archive()

        self.assertFalse(log.active)

    def test_action_unarchive(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "active": False,
            }
        )

        self.assertFalse(log.active)

        log.action_unarchive()

        self.assertTrue(log.active)

    def test_action_set_done(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "state": "new",
            }
        )

        self.assertEqual(log.state, "new")

        log.action_set_done()

        self.assertEqual(log.state, "done")

    def test_action_set_cancelled(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "state": "new",
            }
        )

        self.assertEqual(log.state, "new")

        log.action_set_cancelled()

        self.assertEqual(log.state, "cancelled")

    def test_state_transitions(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.insurance_product.id,
                "state": "new",
            }
        )

        log.write({"state": "running"})
        self.assertEqual(log.state, "running")

        log.action_set_done()
        self.assertEqual(log.state, "done")

    def test_a_log_cannot_be_born_cancelled(self):
        """`write` has always enforced the transition table; `create` did not,
        so a row could be seeded in a state whose only exit is back to New."""
        with self.assertRaises(UserError):
            self.ProductAssetLog.create(
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.insurance_product.id,
                    "state": "cancelled",
                }
            )

    def test_a_producer_may_still_book_a_finished_log(self):
        """A settled vendor bill and a finished maintenance move both create
        their log directly in `done`; refusing that would break them."""
        for state in ("new", "running", "done"):
            log = self.ProductAssetLog.create(
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.insurance_product.id,
                    "state": state,
                }
            )
            self.assertEqual(log.state, state)

    def test_invoice_reference(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "inv_ref": "INV-2024-001",
            }
        )

        self.assertEqual(log.inv_ref, "INV-2024-001")

    def test_notes_field(self):
        notes_text = "Routine maintenance performed. All systems check OK."

        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.maintenance_product.id,
                "notes": notes_text,
            }
        )

        self.assertEqual(log.notes, notes_text)

    def test_product_category_related(self):
        category = self.env["product.category"].create(
            {
                "name": "Test Category",
            }
        )

        self.fuel_product.categ_id = category

        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )

        self.assertEqual(log.product_category_id, category)

    def test_company_default(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )

        self.assertEqual(log.company_id, self.env.company)

    def test_currency_related_to_company(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )

        self.assertEqual(log.currency_id, self.env.company.currency_id)

    def test_state_is_tracked(self):
        self.assertTrue(self.ProductAssetLog._fields["state"].tracking)

    def test_amount_is_tracked(self):
        self.assertTrue(self.ProductAssetLog._fields["amount"].tracking)

    def test_multiple_logs_for_same_asset(self):
        logs = self.ProductAssetLog.create(
            [
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.fuel_product.id,
                    "amount": 500.0,
                    "odometer": 10000.0,
                },
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.fuel_product.id,
                    "amount": 600.0,
                    "odometer": 10500.0,
                },
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.maintenance_product.id,
                    "amount": 1500.0,
                    "odometer": 11000.0,
                },
            ]
        )

        self.assertEqual(len(logs), 3)
        self.assertTrue(all(log.trace_id == self.asset for log in logs))

    def test_odometer_sequence_forward_check(self):
        today = fields.Date.context_today(self.ProductAssetLog)
        self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "date": today,
                "odometer": 20000.0,
            }
        )
        with self.assertRaises(ValidationError):
            self.ProductAssetLog.create(
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.fuel_product.id,
                    "date": today - timedelta(days=7),
                    "odometer": 30000.0,
                }
            )

    def test_odometer_sequence_backward_check(self):
        today = fields.Date.context_today(self.ProductAssetLog)
        self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "date": today + timedelta(days=10),
                "odometer": 50000.0,
            }
        )
        with self.assertRaises(ValidationError):
            self.ProductAssetLog.create(
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": self.fuel_product.id,
                    "date": today + timedelta(days=20),
                    "odometer": 40000.0,
                }
            )

    def test_odometer_same_day_downward_correction_allowed(self):
        today = fields.Date.context_today(self.ProductAssetLog)
        self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "date": today,
                "odometer": 15000.0,
            }
        )
        self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
                "date": today,
                "odometer": 12000.0,
            }
        )

    def test_ondelete_cascade(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )

        asset = self.asset.asset_id

        self.asset.unlink()
        self.assertTrue(log.exists(), "the ledger outlives the serial")
        self.assertEqual(log.asset_id, asset)
        self.assertFalse(log.trace_id)

        asset.unlink()
        self.assertFalse(log.exists())

    def test_group_expand_state(self):
        field_info = self.ProductAssetLog._fields["state"]
        self.assertTrue(field_info.group_expand)

    def _make_fuel_category_product(self):
        categ = self.env["product.category"].create(
            {"name": "Test Fuel Category", "log_type": "fuel"}
        )
        return self.env["product.product"].create(
            {
                "name": "Diesel (fuel-typed)",
                "type": "service",
                "categ_id": categ.id,
            }
        )

    def test_log_type_related_propagation(self):
        fuel_product = self._make_fuel_category_product()
        log = self.ProductAssetLog.create(
            {"asset_id": self.asset.asset_id.id, "product_id": fuel_product.id}
        )
        self.assertEqual(log.log_type, "fuel")

    def test_efficiency_multi_log(self):
        fuel_product = self._make_fuel_category_product()
        today = fields.Date.context_today(self.ProductAssetLog)
        first = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": fuel_product.id,
                "date": today - timedelta(days=10),
                "odometer": 10000.0,
                "qty_fuel": 40.0,
            }
        )
        second = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": fuel_product.id,
                "date": today,
                "odometer": 10500.0,
                "qty_fuel": 50.0,
            }
        )
        self.assertEqual(first.efficiency, 0.0)
        self.assertAlmostEqual(second.efficiency, 10.0, places=4)

    def test_efficiency_zero_when_odometer_regresses(self):
        fuel_product = self._make_fuel_category_product()
        today = fields.Date.context_today(self.ProductAssetLog)
        self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": fuel_product.id,
                "date": today - timedelta(days=5),
                "odometer": 20000.0,
                "qty_fuel": 30.0,
            }
        )
        equal = self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": fuel_product.id,
                "date": today,
                "odometer": 20000.0,
                "qty_fuel": 25.0,
            }
        )
        self.assertEqual(equal.efficiency, 0.0)

    def test_qty_fuel_negative_rejected(self):
        fuel_product = self._make_fuel_category_product()
        self.ProductAssetLog.create(
            {
                "asset_id": self.asset.asset_id.id,
                "product_id": fuel_product.id,
                "qty_fuel": 0.0,
            }
        )
        with self.assertRaises(ValidationError):
            self.ProductAssetLog.create(
                {
                    "asset_id": self.asset.asset_id.id,
                    "product_id": fuel_product.id,
                    "qty_fuel": -1.0,
                }
            )
