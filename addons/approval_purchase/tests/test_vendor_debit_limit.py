from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestVendorDebitLimit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)],
        ).write({"active": False})

        cls.vendor = cls.env["res.partner"].create(
            {"name": "Debit Vendor", "supplier_rank": 1},
        )
        cls.product = cls.env["product.product"].create(
            {
                "name": "Debit Product",
                "type": "consu",
                "seller_ids": [
                    Command.create(
                        {"partner_id": cls.vendor.id, "min_qty": 0.0, "price": 10.0},
                    ),
                ],
            },
        )

    def _category(self, threshold, **values):
        return self.env["approval.category"].create(
            {
                "name": f"Debit Category {threshold}",
                "approval_type": "purchase",
                "approval_minimum": 1,
                "order_approval_mode": "debit",
                "check_debit_limit": True,
                "debit_limit_threshold": threshold,
                **values,
            },
        )

    def _order(self, price):
        return self.env["purchase.order"].create(
            {
                "partner_id": self.vendor.id,
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

    def test_order_below_the_threshold_does_not_match(self):
        category = self._category(5000.0)
        order = self._order(100.0)

        self.assertFalse(category._is_vendor_debit_exceeded(order))
        self.assertFalse(category._is_matching_credit_policy(order))
        self.assertFalse(category._is_applicable_for(order))

    def test_order_above_the_threshold_matches(self):
        category = self._category(500.0)

        self.assertTrue(category._is_vendor_debit_exceeded(self._order(1150.0)))
        self.assertTrue(category._is_applicable_for(self._order(1150.0)))

    def test_a_zero_threshold_is_refused_instead_of_being_inert(self):
        with self.assertRaises(ValidationError):
            self._category(0.0)

    def test_unticking_the_box_frees_the_threshold(self):
        category = self._category(500.0)

        category.write({"check_debit_limit": False, "debit_limit_threshold": 0.0})

        self.assertTrue(
            category._is_matching_credit_policy(self._order(1150.0)),
            "an untouched credit criterion constrains nothing",
        )

    def test_shared_category_threshold_uses_the_order_company_currency(self):
        shared = self._category(1000.0, company_id=False, name="Debit Shared")

        self.assertFalse(
            shared.company_currency_id,
            "a category shared by every company has no currency of its own",
        )
        self.assertTrue(shared._is_vendor_debit_exceeded(self._order(1500.0)))
        self.assertFalse(shared._is_vendor_debit_exceeded(self._order(500.0)))

    def test_company_scoped_threshold_is_converted_into_the_order_currency(self):
        order_currency = self.env.company.currency_id
        foreign_currency = self.env.ref("base.EUR")
        if foreign_currency == order_currency:
            foreign_currency = self.env.ref("base.USD")
        foreign_currency.active = True
        self.env["res.currency.rate"].create(
            {
                "currency_id": foreign_currency.id,
                "company_id": self.env.company.id,
                "rate": 2.0,
                "name": "2020-01-01",
            },
        )
        foreign_company = self.env["res.company"].create(
            {"name": "Debit Foreign Company", "currency_id": foreign_currency.id},
        )
        category = self._category(
            1000.0,
            company_id=foreign_company.id,
            name="Debit Category foreign",
        )
        order = self._order(600.0)

        self.assertEqual(category.company_currency_id, foreign_currency)
        self.assertEqual(order.company_id.currency_id, order_currency)
        self.assertTrue(
            category._is_vendor_debit_exceeded(order),
            "1000 in the category currency is 500 in the order currency, and "
            "the order is worth 600 there: comparing the raw numbers "
            "(600 > 1000) would have said no",
        )
