from odoo.tests import tagged

from .common import AccountApprovalCommon


@tagged("post_install", "-at_install")
class TestCategoryApplicability(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.customer_standard = cls.env["res.partner"].create(
            {
                "name": "Standard Customer",
                "customer_rank": 1,
            },
        )

        cls.customer_special = cls.env["res.partner"].create(
            {
                "name": "Special Customer",
                "customer_rank": 1,
            },
        )

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

        cls.category_amount = cls.env["approval.category"].create(
            {
                "name": "Amount-Based",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
                "move_amount_min": 1000.0,
                "move_amount_max": 10000.0,
            },
        )

        cls.category_customer = cls.env["approval.category"].create(
            {
                "name": "Customer-Based",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
                "move_partner_ids": [(6, 0, [cls.customer_special.id])],
            },
        )

        cls.category_vendor = cls.env["approval.category"].create(
            {
                "name": "Vendor-Based",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
                "move_partner_ids": [(6, 0, [cls.vendor_special.id])],
            },
        )

        cls.category_creation = cls.env["approval.category"].create(
            {
                "name": "Creation Flow",
                "approval_type": "accounting",
                "target_model": "account.move",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )

    def test_amount_based_category_matches_invoice(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_standard.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 30.0,
                            "price_unit": 100.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            self.category_amount._is_applicable_for(invoice),
            "Amount-based category should match invoice in range",
        )

    def test_amount_based_category_does_not_match_below_min(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_standard.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 5.0,
                            "price_unit": 100.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_amount._is_applicable_for(invoice),
            "Amount-based category should not match invoice below minimum",
        )

    def test_amount_based_category_does_not_match_above_max(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_standard.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 150.0,
                            "price_unit": 100.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_amount._is_applicable_for(invoice),
            "Amount-based category should not match invoice above maximum",
        )

    def test_customer_based_category_matches(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_special.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            self.category_customer._is_applicable_for(invoice),
            "Customer-based category should match special customer",
        )

    def test_customer_based_category_does_not_match_other_customer(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_standard.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_customer._is_applicable_for(invoice),
            "Customer-based category should not match other customers",
        )

    def test_vendor_based_category_matches_bill(self):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor_special.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.account_expense.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            self.category_vendor._is_applicable_for(bill),
            "Vendor-based category should match special vendor",
        )

    def test_vendor_based_category_does_not_match_invoice(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_special.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_vendor._is_applicable_for(invoice),
            "Vendor-based category should not match customer invoices",
        )

    def test_creation_flow_category_never_matches_mixin(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_standard.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 50.0,
                            "price_unit": 100.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            self.category_creation._is_applicable_for(invoice),
            "Creation flow category should never match mixin flow",
        )

    def test_category_with_no_restrictions_matches_nothing(self):
        category_all = self.env["approval.category"].create(
            {
                "name": "All Invoices",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
            },
        )

        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer_standard.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 10.0,
                            "account_id": self.account_revenue.id,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            category_all._is_applicable_for(invoice),
            "Category without criteria should not match any move",
        )

    def test_amount_based_category_matches_bill(self):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor_standard.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 30.0,
                            "price_unit": 100.0,
                            "account_id": self.account_expense.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            self.category_amount._is_applicable_for(bill),
            "Amount-based category should match bill in range",
        )
