from odoo.tests import tagged

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestApprovalRequirements(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.customer = cls.env["res.partner"].create(
            {
                "name": "Normal Customer",
                "customer_rank": 1,
                "invoice_approval_required": False,
            },
        )

        cls.flagged_customer = cls.env["res.partner"].create(
            {
                "name": "Flagged Customer",
                "customer_rank": 1,
                "invoice_approval_required": True,
            },
        )

        cls.vendor = cls.env["res.partner"].create(
            {
                "name": "Normal Vendor",
                "supplier_rank": 1,
                "bill_approval_required": False,
            },
        )

        cls.flagged_vendor = cls.env["res.partner"].create(
            {
                "name": "Flagged Vendor",
                "supplier_rank": 1,
                "bill_approval_required": True,
            },
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
                "standard_price": 75.0,
            },
        )

        cls.invoice_category = cls.env["approval.category"].create(
            {
                "name": "Standard Invoice Approval",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
                "move_amount_min": 1000.0,
                "move_amount_max": 10000.0,
            },
        )

        add_category_approver(cls.invoice_category, cls.approver, required=True)

    def test_approval_required_invoice_by_amount(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
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
            invoice.approval_required,
            "Invoice above threshold requires approval",
        )

    def test_no_approval_invoice_below_threshold(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
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
            invoice.approval_required,
            "Invoice below threshold doesn't require approval",
        )

    def test_approval_required_for_flagged_customer(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.flagged_customer.id,
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
            invoice.approval_required,
            "Flagged customer requires approval regardless of amount",
        )

    def test_approval_required_bill_by_amount(self):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 30.0,
                            "price_unit": 75.0,
                            "account_id": self.account_expense.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            bill.approval_required,
            "Bill above threshold requires approval",
        )

    def test_approval_required_for_flagged_vendor(self):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.flagged_vendor.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 75.0,
                            "account_id": self.account_expense.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            bill.approval_required,
            "Flagged vendor requires approval regardless of amount",
        )

    def test_no_approval_for_move_from_approved_request(self):
        creation_category = self.env["approval.category"].create(
            {
                "name": "Bill Request",
                "approval_type": "accounting",
                "target_model": "account.move",
                "approval_minimum": 1,
                "has_product": "required",
            },
        )

        add_category_approver(creation_category, self.approver, required=True)

        approval = self.env["approval.request"].create(
            {
                "name": "Test Bill Request",
                "category_id": creation_category.id,
                "partner_id": self.flagged_vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 100.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": "Test",
                        },
                    ),
                ],
            },
        )

        approval.action_confirm()
        approval.with_user(self.approver).action_approve()

        approval.action_create_account_moves()
        move = approval.line_ids.account_move_line_id.move_id

        self.assertFalse(
            move.approval_required,
            "Move from approved request should not require re-approval",
        )

    def test_approval_requirement_recomputes_on_amount_change(self):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
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

        self.assertFalse(invoice.approval_required, "Initially below threshold")

        invoice.invoice_line_ids.quantity = 30.0

        invoice._compute_approval_required()

        self.assertTrue(
            invoice.approval_required,
            "Should require approval after amount increase",
        )

    def test_no_category_found_means_no_approval(self):
        self.invoice_category.write(
            {"move_amount_min": 20000.0, "move_amount_max": 30000.0}
        )

        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.customer.id,
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

        self.assertFalse(
            invoice.approval_required,
            "No matching category means no approval",
        )

    def test_journal_entry_no_approval(self):
        entry = self.env["account.move"].create(
            {
                "move_type": "entry",
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "account_id": self.account_revenue.id,
                            "debit": 5000.0,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "account_id": self.account_expense.id,
                            "credit": 5000.0,
                        },
                    ),
                ],
            },
        )

        self.assertFalse(
            entry.approval_required,
            "General journal entries don't require approval",
        )

    def test_refund_approval_same_as_invoice(self):
        refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.flagged_customer.id,
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
            refund.approval_required,
            "Customer refund with flagged customer requires approval",
        )

        vendor_refund = self.env["account.move"].create(
            {
                "move_type": "in_refund",
                "partner_id": self.flagged_vendor.id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 75.0,
                            "account_id": self.account_expense.id,
                        },
                    ),
                ],
            },
        )

        self.assertTrue(
            vendor_refund.approval_required,
            "Vendor refund with flagged vendor requires approval",
        )
