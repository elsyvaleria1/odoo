from odoo.fields import Command
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestApprovalModeCriteria(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")

        cls.env["approval.category"].search(
            [("approval_type", "=", "sale"), ("target_model", "=", False)],
        ).write({"active": False})

        cls.customer = cls.env["res.partner"].create(
            {"name": "Mode Customer", "customer_rank": 1},
        )
        cls.other_customer = cls.env["res.partner"].create(
            {"name": "Other Customer", "customer_rank": 1},
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Mode Product", "type": "consu"},
        )

    def _make_category(self, **values):
        return self.env["approval.category"].create(
            {
                "name": "Mode Category",
                "approval_type": "sale",
                "target_model": False,
                "approval_minimum": 1,
                "company_id": self.company.id,
                **values,
            },
        )

    def _make_order(self, price=5000.0, partner=None):
        return self.env["sale.order"].create(
            {
                "partner_id": (partner or self.customer).id,
                "company_id": self.company.id,
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

    def test_new_sale_category_defaults_to_combined(self):
        category = self.env["approval.category"].create(
            {"name": "Defaulted Category", "approval_type": "sale"},
        )

        self.assertEqual(category.so_approval_mode, "combined")

    def test_an_unset_trigger_hides_nothing(self):
        category = self._make_category(
            so_approval_mode=False,
            order_amount_min=100.0,
            order_amount_max=900.0,
            order_partner_ids=[Command.set(self.other_customer.ids)],
            check_credit_limit=True,
        )

        self.assertEqual(category._get_approval_mode_hidden_criteria(), ())

    def test_clearing_the_trigger_keeps_the_configured_criteria(self):
        category = self._make_category(
            so_approval_mode="amount",
            order_amount_min=100.0,
            order_amount_max=900.0,
        )

        with Form(category) as form:
            form.so_approval_mode = False

        self.assertEqual(category.order_amount_min, 100.0)
        self.assertEqual(category.order_amount_max, 900.0)

    def test_a_wiped_category_would_match_every_order(self):
        category = self._make_category(so_approval_mode="combined")

        self.assertTrue(
            category._is_applicable_for(self._make_order(price=100000.0)),
        )

    def test_switching_trigger_still_clears_what_it_hides(self):
        category = self._make_category(
            so_approval_mode="partner",
            order_partner_ids=[Command.set(self.other_customer.ids)],
        )

        form_category = category.new(origin=category)
        form_category.so_approval_mode = "amount"
        form_category._onchange_so_approval_mode()

        self.assertFalse(form_category.order_partner_ids)

    def test_a_hidden_criterion_still_constrains_matching(self):
        category = self._make_category(
            so_approval_mode="amount",
            order_amount_min=100.0,
            order_partner_ids=[Command.set(self.other_customer.ids)],
        )
        order = self._make_order(price=5000.0)

        self.assertTrue(category._is_matching_amount(order))
        self.assertFalse(category._is_matching_partner(order))
        self.assertFalse(category._is_applicable_for(order))

    def test_product_ids_is_governed_by_the_trigger(self):
        category = self._make_category(
            so_approval_mode="amount",
            order_amount_min=100.0,
            has_product="required",
            product_ids=[Command.set(self.product.ids)],
        )

        self.assertIn("product_ids", category._get_approval_mode_hidden_criteria())

    def test_switching_away_from_product_clears_product_ids(self):
        category = self._make_category(
            so_approval_mode="product",
            has_product="required",
            product_ids=[Command.set(self.product.ids)],
        )

        form_category = category.new(origin=category)
        form_category.so_approval_mode = "amount"
        form_category._onchange_so_approval_mode()

        self.assertFalse(form_category.product_ids)

    def test_the_product_trigger_keeps_product_ids(self):
        category = self._make_category(
            so_approval_mode="product",
            has_product="required",
            product_ids=[Command.set(self.product.ids)],
        )

        self.assertNotIn(
            "product_ids",
            category._get_approval_mode_hidden_criteria(),
        )

    def test_product_ids_narrows_matching(self):
        other_product = self.env["product.product"].create(
            {"name": "Unlisted Product", "type": "consu"},
        )
        category = self._make_category(
            so_approval_mode="product",
            has_product="required",
            product_ids=[Command.set(self.product.ids)],
        )
        order = self.env["sale.order"].create(
            {
                "partner_id": self.customer.id,
                "company_id": self.company.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": other_product.id,
                            "product_qty": 1.0,
                            "price_unit": 5000.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(category._is_matching_product(order))
        self.assertFalse(category._is_applicable_for(order))
