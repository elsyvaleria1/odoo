from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestInventoryAdjustmentApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.shelf = cls.env["stock.location"].create(
            {
                "name": "Counted Shelf",
                "usage": "internal",
                "location_id": cls.stock_location.id,
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Counted Product", "is_storable": True}
        )
        cls.other_product = cls.env["product.product"].create(
            {"name": "Other Counted Product", "is_storable": True}
        )
        cls.counter = new_test_user(
            cls.env,
            login="inventory_counter",
            groups="base.group_user,stock.group_stock_user",
        )
        cls.approver = new_test_user(
            cls.env,
            login="inventory_approver",
            groups="base.group_user,stock.group_stock_manager",
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Inventory Adjustment Approval",
                "approval_type": "stock_inventory",
                "company_id": cls.company.id,
                "approval_minimum": 1,
                "step_ids": pool_step([(cls.approver.id, True, 10)], minimum=1),
            }
        )
        cls.date_counted = fields.Datetime.now() - timedelta(days=2)

    def _counted_quant(self, product, on_hand, counted, location=None):
        location = location or self.stock_location
        Quant = self.env["stock.quant"]
        Quant._update_available_quantity(product, location, on_hand)
        quant = Quant._gather(product, location)
        quant.with_context(inventory_mode=True).inventory_quantity = counted
        return quant

    def _batch(self, quants):
        return (
            self.env["stock.inventory.adjustment"]
            .with_user(self.counter)
            ._create_from_quants(quants, "Cycle count", self.date_counted)
        )

    def _requested_batch(self, quants):
        batch = self._batch(quants)
        batch.action_create_approval_request()
        return batch

    def test_counted_quants_become_a_batch_with_their_on_hand_snapshot(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)

        batch = self._batch(quant)

        self.assertEqual(batch.state, "draft")
        self.assertEqual(batch.date_counted, self.date_counted)
        self.assertRecordValues(
            batch.line_ids,
            [
                {
                    "quant_id": quant.id,
                    "product_id": self.product.id,
                    "location_id": self.stock_location.id,
                    "quantity_counted": 7.0,
                    "quantity_on_hand": 10.0,
                    "quantity_difference": -3.0,
                }
            ],
        )

    def test_a_batch_needs_a_counted_quant(self):
        quant = self._counted_quant(self.product, on_hand=4.0, counted=4.0)
        quant.action_clear_inventory_quantity()

        with self.assertRaises(UserError):
            self._batch(quant)

    def test_requesting_approval_locks_the_lines(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        batch = self._requested_batch(quant)

        self.assertEqual(batch.approval_state, "pending")
        self.assertEqual(batch.approval_request_id.category_id, self.category)
        with self.assertRaises(UserError):
            batch.line_ids.with_user(self.counter).quantity_counted = 5.0
        with self.assertRaises(UserError):
            batch.with_user(self.counter).date_counted = fields.Datetime.now()

    def test_approval_applies_the_counts_at_the_counting_date(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        batch = self._requested_batch(quant)

        batch.approval_request_id.with_user(self.approver).action_approve()

        self.assertEqual(batch.state, "applied")
        self.assertEqual(quant.quantity, 7.0)
        self.assertFalse(quant.inventory_quantity_set)
        move = self.env["stock.move"].search(
            [("product_id", "=", self.product.id), ("is_inventory", "=", True)]
        )
        self.assertEqual(len(move), 1)
        self.assertEqual(move.date, self.date_counted)
        self.assertEqual(move.product_uom_qty, 3.0)
        self.assertEqual(move.reference, batch.name)

    def test_a_quant_that_moved_since_the_request_refuses_the_whole_apply(self):
        moved = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        steady = self._counted_quant(self.other_product, on_hand=5.0, counted=6.0)
        batch = self._requested_batch(moved | steady)
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, 2.0
        )

        batch.approval_request_id.with_user(self.approver).action_approve()

        self.assertEqual(batch.state, "cancelled")
        self.assertEqual(moved.quantity, 12.0)
        self.assertEqual(steady.quantity, 5.0)
        self.assertEqual(steady.inventory_quantity, 6.0)
        self.assertTrue(steady.inventory_quantity_set)
        self.assertFalse(
            self.env["stock.move"].search(
                [
                    ("product_id", "in", (self.product | self.other_product).ids),
                    ("is_inventory", "=", True),
                ]
            )
        )
        self.assertTrue(
            any(
                self.product.display_name in message.body
                for message in batch.message_ids
            )
        )

    def test_refusal_leaves_the_counts_on_the_quants(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        batch = self._requested_batch(quant)

        batch.approval_request_id.with_user(self.approver).with_context(
            skip_wizard=True
        ).action_refuse()

        self.assertEqual(batch.state, "cancelled")
        self.assertEqual(quant.quantity, 10.0)
        self.assertEqual(quant.inventory_quantity, 7.0)
        self.assertTrue(quant.inventory_quantity_set)

    def test_a_refused_request_reset_to_draft_makes_the_batch_editable_again(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        batch = self._requested_batch(quant)
        batch.approval_request_id.with_user(self.approver).with_context(
            skip_wizard=True
        ).action_refuse()
        self.assertEqual(batch.state, "cancelled")

        batch.approval_request_id.action_reset_to_draft()

        self.assertEqual(batch.state, "draft")
        batch.line_ids.with_user(self.counter).quantity_counted = 8.0
        self.assertEqual(batch.line_ids.quantity_difference, -2.0)

    def test_an_applied_batch_cannot_be_applied_twice(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        batch = self._requested_batch(quant)
        batch.approval_request_id.with_user(self.approver).action_approve()

        with self.assertRaises(UserError):
            batch._apply()

    def test_an_applied_batch_keeps_its_approval(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        batch = self._requested_batch(quant)
        batch.approval_request_id.with_user(self.approver).action_approve()

        request = batch.approval_request_id.with_env(self.env)
        with self.assertRaisesRegex(UserError, "already went through"):
            request.action_reset_to_draft()
        self.assertEqual(batch.approval_state, "approved")

    def test_a_batch_cancelled_for_moved_stock_stays_closed_after_a_reset(self):
        quant = self._counted_quant(self.product, on_hand=10.0, counted=7.0)
        batch = self._requested_batch(quant)
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.stock_location, 2.0
        )
        batch.approval_request_id.with_user(self.approver).action_approve()
        self.assertEqual(batch.state, "cancelled")

        batch.approval_request_id.with_env(self.env).action_reset_to_draft()

        self.assertEqual(batch.approval_state, "new")
        self.assertEqual(batch.state, "cancelled")
        self.assertTrue(self._batch(quant))

    def test_category_criteria_select_the_batch_by_location_and_product_category(self):
        quant = self._counted_quant(
            self.product, on_hand=3.0, counted=1.0, location=self.shelf
        )
        batch = self._batch(quant)
        elsewhere = self.env["stock.location"].create(
            {"name": "Elsewhere", "usage": "internal"}
        )
        self.category.location_ids = elsewhere

        self.assertFalse(self.category._is_applicable_for(batch))

        self.category.location_ids = self.shelf
        self.assertTrue(self.category._is_applicable_for(batch))

        self.category.stock_product_categ_ids = self.env["product.category"].create(
            {"name": "Not this product's"}
        )
        self.assertFalse(self.category._is_applicable_for(batch))

    def test_a_stock_transfer_category_does_not_serve_a_batch(self):
        quant = self._counted_quant(self.product, on_hand=3.0, counted=1.0)
        batch = self._batch(quant)
        transfer_category = self.env["approval.category"].create(
            {"name": "Transfers", "approval_type": "stock", "approval_minimum": 1}
        )

        self.assertNotIn(transfer_category, batch._get_candidate_approval_categories())

    def test_each_adjustment_of_a_recordset_is_judged_on_its_own_lines(self):
        self.env["approval.category"].search(
            [("approval_type", "=", "stock_inventory"), ("id", "!=", self.category.id)]
        ).active = False
        self.category.location_ids = self.shelf
        on_shelf = self._batch(
            self._counted_quant(
                self.product, on_hand=3.0, counted=1.0, location=self.shelf
            )
        )
        elsewhere = self._batch(
            self._counted_quant(self.other_product, on_hand=3.0, counted=1.0)
        )
        for adjustments in (on_shelf | elsewhere, elsewhere | on_shelf):
            with self.subTest(first=adjustments[:1].id):
                adjustments.invalidate_recordset(["approval_required"])
                required = adjustments.mapped("approval_required")
                self.assertEqual(
                    dict(zip(adjustments, required, strict=True)),
                    {on_shelf: True, elsewhere: False},
                )
