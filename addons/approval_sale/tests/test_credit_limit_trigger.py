from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestCreditLimitTrigger(TransactionCase):
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
                "name": "Credit Salesperson",
                "login": "credit_salesperson",
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
                "name": "Credit Customer",
                "customer_rank": 1,
                "property_payment_term_id": cls.env.ref(
                    "payment_term.account_payment_term_immediate"
                ).id,
            },
        )
        customer = cls.customer.with_company(cls.company).sudo()
        if "credit_trusted_amount" in customer._fields:
            customer.credit_trusted_amount = 1.0
        else:
            customer.credit_limit = 1.0

        cls.product = cls.env["product.product"].create(
            {"name": "Credit Product", "type": "consu"},
        )

        cls.category = cls.env["approval.category"].create(
            {
                "name": "Credit Category",
                "approval_type": "sale",
                "target_model": False,
                "approval_minimum": 1,
                "so_approval_mode": "credit",
                "check_credit_limit": True,
                "company_id": cls.company.id,
                "step_ids": pool_step([(cls.env.user.id, True, 10)], minimum=1),
            },
        )

    def _make_order(self, price=20000.0):
        return self.env["sale.order"].create(
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

    def test_salesperson_is_in_neither_accounting_group(self):
        self.assertFalse(
            self.salesperson.has_group("account.group_account_invoice"),
        )
        self.assertFalse(
            self.salesperson.has_group("account.group_account_readonly"),
        )

    def test_salesperson_can_match_a_credit_category(self):
        order = self._make_order()

        self.assertTrue(
            self.category.with_user(self.salesperson)._is_matching_credit_policy(
                order.with_user(self.salesperson),
            ),
        )

    def test_salesperson_can_confirm_an_order_under_a_credit_category(self):
        order = self._make_order()

        order.with_user(self.salesperson).action_confirm()

        self.assertEqual(order.approval_request_id.category_id, self.category)

    def test_the_credit_check_still_answers_correctly(self):
        order = self._make_order(price=20000.0)
        self.assertTrue(self.category._check_customer_credit_exceeded(order))

        self.customer.with_company(self.company).sudo().credit_limit = 0.0
        self.assertFalse(self.category._check_customer_credit_exceeded(order))
