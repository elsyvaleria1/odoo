from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPurchaseOrderLineGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)],
        ).write({"active": False})

        cls.env.company.write(
            {
                "po_validation_level": "module_approval",
                "po_auto_confirm_on_approval": False,
            },
        )

        cls.manager = cls.env["res.users"].create(
            {
                "name": "Guard Manager",
                "login": "guard_manager",
                "group_ids": [
                    Command.set([cls.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )
        cls.approver = cls.env["res.users"].create(
            {
                "name": "Guard Approver",
                "login": "guard_approver",
                "group_ids": [
                    Command.set([cls.env.ref("purchase.group_purchase_manager").id]),
                ],
            },
        )
        cls.vendor = cls.env["res.partner"].create(
            {"name": "Guard Vendor", "supplier_rank": 1},
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Guard Product",
                "type": "consu",
                "seller_ids": [
                    Command.create(
                        {"partner_id": cls.vendor.id, "min_qty": 0.0, "price": 10.0},
                    ),
                ],
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Guard Purchase Approval",
                "approval_type": "purchase",
                "approval_minimum": 1,
                "order_approval_mode": "amount",
                "order_amount_min": 1.0,
            },
        )
        add_category_approver(cls.category, cls.approver, required=True)

    def _pending_order(self):
        order = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 23.0,
                        },
                    ),
                ],
            },
        )
        order.invalidate_recordset()
        order.action_confirm()
        self.assertEqual(order.approval_state, "pending")
        return order

    def test_manager_cannot_add_a_line_while_pending(self):
        order = self._pending_order()
        amount_before = order.amount_total

        with self.assertRaises(UserError):
            self.env["purchase.order.line"].with_user(self.manager).create(
                {
                    "order_id": order.id,
                    "product_id": self.product.id,
                    "product_qty": 500.0,
                    "price_unit": 11.5,
                },
            )

        self.assertEqual(
            order.amount_total,
            amount_before,
            "approvers must not have the total move under them",
        )

    def test_manager_cannot_delete_a_line_while_pending(self):
        order = self._pending_order()

        with self.assertRaises(UserError):
            order.line_ids.with_user(self.manager).unlink()

        self.assertTrue(order.line_ids)

    def test_manager_cannot_edit_a_line_while_pending(self):
        order = self._pending_order()

        with self.assertRaises(UserError):
            order.line_ids.with_user(self.manager).write({"product_qty": 99.0})

    def test_manager_cannot_move_a_line_out_of_a_pending_order(self):
        order = self._pending_order()
        destination = self.env["purchase.order"].create({"partner_id": self.vendor.id})
        amount_before = order.amount_total

        with self.assertRaises(UserError):
            order.line_ids.with_user(self.manager).write({"order_id": destination.id})

        self.assertTrue(order.line_ids, "the pending order must keep its line")
        self.assertEqual(order.amount_total, amount_before)
        self.assertFalse(destination.line_ids)

    def test_manager_cannot_move_a_line_into_a_pending_order(self):
        order = self._pending_order()
        source = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 7.0,
                            "price_unit": 10.0,
                        },
                    ),
                ],
            },
        )
        amount_before = order.amount_total

        with self.assertRaises(UserError):
            source.line_ids.with_user(self.manager).write({"order_id": order.id})

        self.assertEqual(
            order.amount_total,
            amount_before,
            "the total must not move under the approvers from the outside either",
        )

    def test_manager_cannot_swap_the_uom_while_pending(self):
        order = self._pending_order()

        with self.assertRaises(UserError):
            order.line_ids.with_user(self.manager).write(
                {"product_uom_id": self.env.ref("base.product_uom_dozen").id},
            )

    def test_manager_cannot_rewrite_the_description_while_pending(self):
        order = self._pending_order()
        description_before = order.line_ids.name

        with self.assertRaises(UserError):
            order.line_ids.with_user(self.manager).write({"name": "SWAPPED"})

        self.assertEqual(order.line_ids.name, description_before)

    def test_lines_move_freely_once_the_approval_is_decided(self):
        order = self._pending_order()

        order.approval_request_id.with_user(self.approver).action_approve()
        order.invalidate_recordset()

        line = (
            self.env["purchase.order.line"]
            .with_user(self.manager)
            .create(
                {
                    "order_id": order.id,
                    "product_id": self.product.id,
                    "product_qty": 2.0,
                    "price_unit": 10.0,
                },
            )
        )
        self.assertTrue(line, "an approved order is editable again")
        line.with_user(self.manager).write(
            {
                "product_uom_id": self.env.ref("base.product_uom_dozen").id,
                "name": "renamed once decided",
            },
        )
        line.with_user(self.manager).unlink()

    def test_the_module_can_still_build_lines_from_an_approved_request(self):
        request_category = self.env["approval.category"].create(
            {
                "name": "Guard Purchase Request",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )
        add_category_approver(request_category, self.approver, required=True)
        request = self.env["approval.request"].create(
            {
                "name": "Guard Request",
                "category_id": request_category.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 10.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": self.product.name,
                        },
                    ),
                ],
            },
        )

        request.action_confirm()
        request.with_user(self.approver).action_approve()
        request.action_create_purchase_orders()

        self.assertTrue(
            request.line_ids.purchase_order_line_id,
            "the guard must not block the request -> purchase order flow",
        )
