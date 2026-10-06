from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCategoryApplicability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        existing_categories = cls.env["approval.category"].search(
            [("approval_type", "=", "purchase"), ("target_model", "=", False)]
        )
        existing_categories.write({"active": False})

        cls.vendor_standard = cls.env["res.partner"].create(
            {
                "name": "Standard Vendor",
                "supplier_rank": 1,
            },
        )

        cls.vendor_special = cls.env["res.partner"].create(
            {
                "name": "Special Vendor",
                "supplier_rank": 1,
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
            },
        )

        cls.category_electronics = cls.env["product.category"].create(
            {
                "name": "Electronics",
            },
        )

        cls.product_electronics = cls.env["product.product"].create(
            {
                "name": "Electronics Product",
                "type": "consu",
                "categ_id": cls.category_electronics.id,
                "list_price": 500.0,
            },
        )

        cls.category_amount = cls.env["approval.category"].create(
            {
                "name": "Amount-Based",
                "approval_type": "purchase",
                "target_model": False,
                "approval_minimum": 1,
                "order_approval_mode": "amount",
                "order_amount_min": 1000.0,
                "order_amount_max": 10000.0,
            },
        )

        cls.category_vendor = cls.env["approval.category"].create(
            {
                "name": "Vendor-Based",
                "approval_type": "purchase",
                "target_model": False,
                "approval_minimum": 1,
                "order_approval_mode": "partner",
                "order_partner_ids": [Command.set([cls.vendor_special.id])],
            },
        )

        cls.category_product = cls.env["approval.category"].create(
            {
                "name": "Product-Based",
                "approval_type": "purchase",
                "target_model": False,
                "approval_minimum": 1,
                "order_approval_mode": "product",
                "product_categ_ids": [Command.set([cls.category_electronics.id])],
            },
        )

        cls.category_creation = cls.env["approval.category"].create(
            {
                "name": "Creation Flow",
                "approval_type": "purchase",
                "target_model": "purchase.order",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )

    def test_amount_based_category_matches(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 30.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            self.category_amount._is_applicable_for(po),
            "Amount-based category should match PO in range",
        )

    def test_amount_based_category_does_not_match_below_min(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 5.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_amount._is_applicable_for(po),
            "Amount-based category should not match PO below minimum",
        )

    def test_amount_based_category_does_not_match_above_max(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 150.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_amount._is_applicable_for(po),
            "Amount-based category should not match PO above maximum",
        )

    def test_vendor_based_category_matches(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_special.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            self.category_vendor._is_applicable_for(po),
            "Vendor-based category should match special vendor",
        )

    def test_vendor_based_category_does_not_match_other_vendor(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_vendor._is_applicable_for(po),
            "Vendor-based category should not match other vendors",
        )

    def test_product_category_based_matches(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product_electronics.id,
                            "product_qty": 1.0,
                            "price_unit": 500.0,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            self.category_product._is_applicable_for(po),
            "Product category-based should match electronics",
        )

    def test_product_category_based_does_not_match_other_products(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_product._is_applicable_for(po),
            "Product category-based should not match other categories",
        )

    def test_creation_flow_category_never_matches_mixin(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 50.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_creation._is_applicable_for(po),
            "Creation flow categories should never match mixin flow",
        )

    def test_get_approval_category_returns_correct_category(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 30.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        category = po._get_approval_category()
        self.assertEqual(
            category,
            self.category_amount,
            "Should return amount-based category",
        )

    def test_get_approval_category_raises_when_no_match(self):
        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_standard.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 1.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        with self.assertRaises(UserError):
            po._get_approval_category()

    def test_category_sequence_determines_priority(self):
        self.category_amount.sequence = 20
        self.category_vendor.sequence = 10

        po = self.env["purchase.order"].create(
            {
                "partner_id": self.vendor_special.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_qty": 30.0,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

        category = po._get_approval_category()

        self.assertEqual(
            category,
            self.category_vendor,
            "Should return category with lower sequence",
        )
