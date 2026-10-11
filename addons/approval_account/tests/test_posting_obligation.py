from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import HttpCase, new_test_user, tagged

from .common import AccountApprovalCommon
from odoo.addons.account.tests.common_posting_obligation import exemption_notes
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPostingObligation(AccountApprovalCommon, HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Bills over 1000",
                "approval_type": "accounting",
                "approval_minimum": 1,
                "move_amount_min": 1000.0,
                "move_auto_post": False,
                "has_amount": "required",
                "has_partner": "required",
            },
        )
        add_category_approver(cls.category, cls.approver, required=True)
        cls.env.ref("approval_account.obligation_move_post").mode = "request"
        cls.clerk = new_test_user(
            cls.env,
            login="posting_obligation_clerk",
            groups="base.group_user,account.group_account_invoice",
        )

    def _bill(self, date="2026-09-01"):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_b.id,
                "invoice_date": date,
                "date": date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Needs approval",
                            "quantity": 30.0,
                            "price_unit": 75.0,
                            "account_id": self.account_expense.id,
                        }
                    )
                ],
            }
        )
        self.assertTrue(bill.approval_required)
        return bill

    def _approved_bill(self):
        bill = self._bill()
        bill.action_post()
        bill.approval_request_id.with_user(self.approver).action_approve()
        self.assertEqual(bill.approval_state, "approved")
        self.assertEqual(bill.state, "draft")
        return bill

    def test_a_direct_post_waits_for_approval(self):
        bill = self._bill()
        scheduled = self._bill(date="2099-01-01")

        self.assertEqual(bill._get_held_for_posting_approval(), bill)
        with self.assertRaisesRegex(UserError, "need an approval"):
            bill._post(soft=False)
        with self.assertRaisesRegex(UserError, "need an approval"):
            bill.sudo()._post(soft=False)
        with self.assertRaisesRegex(UserError, "need an approval"):
            scheduled._post(soft=True)

        self.assertEqual(bill.state, "draft")
        self.assertEqual(scheduled.auto_post, "no")
        self.assertFalse(bill.approval_request_id, "a direct post cannot ask")

    def test_an_approved_bill_posts_on_any_path(self):
        bill = self._approved_bill()

        self.assertFalse(bill._get_held_for_posting_approval())
        bill._post(soft=False)

        self.assertEqual(bill.state, "posted")
        self.assertFalse(exemption_notes(bill, "payment_received"))

    def test_an_exemption_posts_through_the_door_without_asking(self):
        bill = self._bill()

        with bill._exempting_posting_from_approval("payment_received"):
            bill.action_post()

        self.assertEqual(bill.state, "posted")
        self.assertFalse(bill.approval_request_id)
        self.assertEqual(len(exemption_notes(bill, "payment_received")), 1)

    def test_a_cancelling_reversal_does_not_wait_for_approval(self):
        bill = self._approved_bill()
        bill._post(soft=False)

        reversal = bill._reverse_moves(
            [{"invoice_date": bill.invoice_date, "date": bill.date}], cancel=True
        )

        self.assertTrue(reversal.approval_required)
        self.assertEqual(reversal.state, "posted")
        self.assertEqual(bill.payment_state, "reversed")
        self.assertEqual(len(exemption_notes(reversal, "reversal_cancel")), 1)

    def _call(self, model, method, args, context):
        return self.url_open(
            f"/web/dataset/call_kw/{model}/{method}",
            json={
                "jsonrpc": "2.0",
                "method": "call",
                "params": {
                    "model": model,
                    "method": method,
                    "args": args,
                    "kwargs": {"context": context},
                },
            },
        ).json()

    def test_a_browser_cannot_forge_an_exemption(self):
        bill = self._bill()
        self.authenticate(self.clerk.login, self.clerk.login)
        context = {
            "posting_approval_exemption": "payment_received",
            "approval_binding_admitted": [["account.move", "post", bill.ids]],
        }

        for method, args in (
            ("_post", [bill.ids]),
            ("_exempting_posting_from_approval", [bill.ids, "payment_received"]),
            ("_record_posting_approval_exemption", [bill.ids, "payment_received"]),
        ):
            with self.subTest(method=method):
                self.assertIn(
                    "error", self._call("account.move", method, args, context)
                )
        posted = self._call("account.move", "action_post", [bill.ids], context)

        self.assertNotIn("error", posted)
        bill.invalidate_recordset()
        self.assertEqual(bill.state, "draft")
        self.assertEqual(bill.approval_state, "pending", "the button asked instead")
        self.assertFalse(exemption_notes(bill, "payment_received"))
