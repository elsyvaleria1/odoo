from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestAccountApprovalFlows(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.accountant = cls.env["res.users"].create(
            {
                "name": "Accountant",
                "login": "accountant",
                "email": "accountant@test.com",
                "group_ids": [(6, 0, [cls.env.ref("account.group_account_user").id])],
            },
        )

        cls.customer = cls.partner_a
        cls.vendor = cls.partner_b

        cls.product = cls.env["product.product"].create(
            {
                "name": "Test Product",
                "type": "consu",
                "list_price": 100.0,
                "standard_price": 75.0,
            },
        )

        cls.category_mixin = cls.env["approval.category"].create(
            {
                "name": "Invoice Approval (Mixin)",
                "approval_type": "accounting",
                "target_model": False,
                "approval_minimum": 1,
                "move_amount_min": 1000.0,
                "move_amount_max": 10000.0,
                "has_amount": "required",
                "has_partner": "required",
            },
        )

        cls.category_creation = cls.env["approval.category"].create(
            {
                "name": "Bill Request (Creation)",
                "approval_type": "accounting",
                "target_model": "account.move",
                "approval_minimum": 1,
                "has_product": "required",
                "has_amount": "optional",
                "has_partner": "optional",
            },
        )

        for category in [cls.category_mixin, cls.category_creation]:
            add_category_approver(category, cls.approver, required=True)

    def test_mixin_flow_invoice_to_approval(self):
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
            "Invoice should require approval (amount = 3000)",
        )
        self.assertFalse(invoice.approval_request_id, "No approval request yet")
        self.assertEqual(invoice.state, "draft")

        invoice.action_post()

        self.assertTrue(
            invoice.approval_request_id,
            "Approval request should be created",
        )
        approval = invoice.approval_request_id
        self.assertEqual(approval.category_id, self.category_mixin)
        self.assertEqual(approval.approval_type, "accounting")
        self.assertFalse(
            approval.target_model,
            "Mixin flow approval has no target_model",
        )
        self.assertEqual(approval.state, "pending", "Approval is pending")
        self.assertEqual(invoice.state, "draft", "Invoice still in draft")

        approval.with_user(self.approver).action_approve()

        self.assertEqual(approval.state, "approved")

    def test_creation_flow_approval_to_bill(self):
        approval = self.env["approval.request"].create(
            {
                "name": "Test Bill Request",
                "category_id": self.category_creation.id,
                "partner_id": self.vendor.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "quantity": 20.0,
                            "price_unit": 75.0,
                            "product_uom_id": self.product.uom_id.id,
                            "description": "Test Product Line",
                        },
                    ),
                ],
            },
        )

        self.assertEqual(approval.state, "new")
        self.assertEqual(approval.target_model, "account.move")
        self.assertEqual(approval.count_account_move, 0, "No bills yet")

        approval.action_confirm()
        self.assertEqual(approval.state, "pending")

        approval.with_user(self.approver).action_approve()
        self.assertEqual(approval.state, "approved")

        approval.action_create_account_moves()

        self.assertEqual(approval.count_account_move, 1, "Bill should be created")
        bill = approval.line_ids.account_move_line_id.move_id

        self.assertEqual(bill.move_type, "in_invoice")
        self.assertEqual(bill.partner_id, self.vendor)
        self.assertFalse(
            bill.approval_required,
            "Bill from approval shouldn't need re-approval",
        )

        bill.action_post()
        self.assertEqual(bill.state, "posted")

    def test_cannot_post_while_approval_pending(self):
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

        invoice.action_create_approval_request()

        with self.assertRaises(UserError, msg="Cannot post during pending approval"):
            invoice.action_post()

    def test_can_post_after_approval_granted(self):
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

        invoice.action_create_approval_request()
        approval = invoice.approval_request_id
        approval.with_user(self.approver).action_approve()

        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def test_cannot_post_if_approval_refused(self):
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

        bill.action_create_approval_request()
        first_approval = bill.approval_request_id
        first_approval.with_user(self.approver).with_context(
            skip_wizard=True,
        ).action_refuse()
        self.assertEqual(first_approval.state, "refused")

        bill.action_post()
        self.assertEqual(bill.state, "draft", "Bill must not post unapproved")
        second_approval = bill.approval_request_id
        self.assertNotEqual(second_approval, first_approval)
        self.assertEqual(second_approval.state, "pending")
        self.assertEqual(first_approval.state, "refused")

    def _bill_needing_approval(self):
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
        bill.action_create_approval_request()
        return bill

    def test_cancelling_a_bill_refuses_its_pending_approval(self):
        bill = self._bill_needing_approval()
        request = bill.approval_request_id
        self.assertEqual(request.state, "pending")
        bill.action_cancel()
        self.assertEqual(bill.state, "cancel")
        self.assertEqual(request.state, "refused")

    def test_resetting_a_bill_to_draft_clears_its_refused_approval(self):
        bill = self._bill_needing_approval()
        request = bill.approval_request_id
        bill.action_cancel()
        bill.action_draft()
        self.assertEqual(bill.state, "draft")
        self.assertFalse(bill.approval_request_id)
        self.assertEqual(request.state, "refused")

    def test_approval_progress_updates(self):
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

        invoice.action_create_approval_request()
        approval = invoice.approval_request_id

        self.assertEqual(invoice.approval_progress, 0.0, "Progress should be 0%")

        approval.with_user(self.approver).action_approve()

        self.assertEqual(invoice.approval_progress, 100.0, "Progress should be 100%")
