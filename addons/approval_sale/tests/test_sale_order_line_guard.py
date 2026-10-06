from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestSaleOrderLineGuard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.company.so_validation_level = "manager_amount"

        cls.env["approval.category"].search(
            [("approval_type", "=", "sale"), ("target_model", "=", False)],
        ).write({"active": False})

        cls.salesperson = cls.env["res.users"].create(
            {
                "name": "Guard Salesperson",
                "login": "guard_salesperson",
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "group_ids": [
                    Command.set(
                        [
                            cls.env.ref("base.group_user").id,
                            cls.env.ref("sale.group_sale_salesman").id,
                        ],
                    ),
                ],
            },
        )

        # Paid immediately, so the order is about what these tests exercise: with
        # account_credit installed, a customer with no credit type is cash-only
        # and a deferred payment term refuses the confirmation before approval.
        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Guard Customer",
                "customer_rank": 1,
                "property_payment_term_id": cls.env.ref(
                    "payment_term.account_payment_term_immediate"
                ).id,
            },
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Guard Product", "type": "consu"},
        )
        cls.extra_product = cls.env["product.product"].create(
            {"name": "Guard Extra Product", "type": "consu"},
        )

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Guard Category",
                "approval_type": "sale",
                "target_model": False,
                "approval_minimum": 1,
                "so_approval_mode": "combined",
                "company_id": cls.company.id,
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            },
        )

    def _pending_order(self, price=20000.0):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "user_id": self.salesperson.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": price,
                        },
                    ),
                ],
            },
        )
        order.with_user(self.salesperson).action_confirm()
        self.assertEqual(order.approval_state, "pending")
        return order

    def test_writing_a_protected_field_is_blocked(self):
        order = self._pending_order()

        with self.assertRaises(UserError):
            order.with_user(self.salesperson).line_ids[0].write({"price_unit": 1.0})

    def test_changing_the_unit_of_measure_is_blocked(self):
        order = self._pending_order()
        total_before = order.amount_total
        dozen = self.env.ref("uom.product_uom_dozen")

        with self.assertRaises(UserError):
            order.with_user(self.salesperson).line_ids[0].write(
                {"product_uom_id": dozen.id},
            )

        self.assertEqual(
            order.amount_total,
            total_before,
            "the unit of measure moves the line total exactly as the price "
            "does, so it must not move while approvers are deciding",
        )
        self.assertEqual(order.approval_request_id.amount, order.amount_total)

    def test_adding_a_line_is_blocked(self):
        order = self._pending_order()
        total_before = order.amount_total

        with self.assertRaises(UserError):
            self.env["sale.order.line"].with_user(self.salesperson).create(
                {
                    "order_id": order.id,
                    "product_id": self.extra_product.id,
                    "product_qty": 50.0,
                    "price_unit": 1000.0,
                },
            )

        self.assertEqual(order.amount_total, total_before)

    def test_moving_a_line_into_a_pending_order_is_blocked(self):
        order = self._pending_order()
        total_before = order.amount_total
        draft = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "user_id": self.salesperson.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.extra_product.id,
                            "product_qty": 50.0,
                            "price_unit": 1000.0,
                        },
                    ),
                ],
            },
        )

        with self.assertRaises(UserError):
            draft.line_ids.with_user(self.salesperson).write({"order_id": order.id})

        self.assertEqual(order.amount_total, total_before)

    def test_rewording_a_line_is_blocked(self):
        order = self._pending_order()

        with self.assertRaises(UserError):
            order.with_user(self.salesperson).line_ids[0].write(
                {"name": "Something else"},
            )

    def test_removing_a_line_is_blocked(self):
        order = self._pending_order()

        with self.assertRaises(UserError):
            order.with_user(self.salesperson).line_ids.unlink()

        self.assertEqual(len(order.line_ids), 1)

    def test_the_approved_amount_still_matches_the_order(self):
        order = self._pending_order()

        with self.assertRaises(UserError):
            self.env["sale.order.line"].with_user(self.salesperson).create(
                {
                    "order_id": order.id,
                    "product_id": self.extra_product.id,
                    "product_qty": 1.0,
                    "price_unit": 500.0,
                },
            )

        self.assertEqual(order.approval_request_id.amount, order.amount_total)

    def test_the_message_names_the_operation(self):
        order = self._pending_order()

        with self.assertRaises(UserError) as caught:
            order.with_user(self.salesperson).line_ids.unlink()
        self.assertIn("add or remove lines", str(caught.exception))

        with self.assertRaises(UserError) as caught:
            order.with_user(self.salesperson).line_ids[0].write({"price_unit": 2.0})
        self.assertIn("price_unit", str(caught.exception))

    def test_lines_move_freely_while_the_order_is_draft(self):
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "user_id": self.salesperson.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        line = (
            self.env["sale.order.line"]
            .with_user(self.salesperson)
            .create(
                {
                    "order_id": order.id,
                    "product_id": self.extra_product.id,
                    "product_qty": 2.0,
                    "price_unit": 50.0,
                },
            )
        )
        line.write({"price_unit": 60.0})
        line.unlink()

        self.assertEqual(len(order.line_ids), 1)

    def test_sudo_is_not_blocked(self):
        order = self._pending_order()

        self.env["sale.order.line"].sudo().create(
            {
                "order_id": order.id,
                "product_id": self.extra_product.id,
                "product_qty": 1.0,
                "price_unit": 10.0,
            },
        )

        self.assertEqual(len(order.line_ids), 2)
