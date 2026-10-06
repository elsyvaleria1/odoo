from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged

from .common import AccountApprovalCommon


@tagged("post_install", "-at_install")
class TestAccountApprovalAbsence(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.product = cls.env["product.product"].create(
            {"name": "Absence Supply", "type": "consu", "list_price": 100.0}
        )
        cls.partner_a.bill_approval_required = True
        cls.categories = cls.env["approval.category"].search(
            [("approval_type", "=", "accounting"), ("target_model", "=", False)]
        )
        cls.shipped = cls.env.ref("approval_account.approval_category_account_move")
        cls.shipped._add_approver(cls.approver, required=True)

    def _new_bill(self):
        return self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2026-06-01",
                "date": "2026-06-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 500.0,
                            "account_id": self.account_expense.id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )

    def test_no_category_configured_asks_no_approval(self):
        self.categories.active = False
        bill = self._new_bill()
        self.assertFalse(bill.approval_required)
        bill.action_post()
        self.assertEqual(bill.state, "posted")
        self.assertFalse(bill.approval_request_id)

    def test_a_configured_category_that_does_not_apply_still_refuses(self):
        self.categories.move_partner_ids = [Command.set(self.partner_b.ids)]
        bill = self._new_bill()
        self.assertTrue(bill.approval_required)
        with self.assertRaisesRegex(UserError, "No approval category found"):
            bill.action_post()

    def test_a_flagged_partner_still_needs_the_category_that_applies(self):
        bill = self._new_bill()
        self.assertTrue(bill.approval_required)
        bill.action_post()
        self.assertEqual(bill.state, "draft")
        self.assertEqual(bill.approval_state, "pending")
