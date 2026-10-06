from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import HttpCase, new_test_user, tagged

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestForgedAdmission(AccountApprovalCommon, HttpCase):
    """The Post entries wizard reaches the posting checkpoint without passing
    `action_post`'s own gate, so the checkpoint alone stands between a bill that
    needs approval and its posting. Nothing a client sends may lift it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        category = cls.env["approval.category"].create(
            {
                "name": "Bills over 1000",
                "approval_type": "accounting",
                "approval_minimum": 1,
                "move_amount_min": 1000.0,
                "has_amount": "required",
                "has_partner": "required",
            },
        )
        add_category_approver(category, cls.approver, required=True)
        cls.env.ref("approval_account.obligation_move_post").mode = "request"
        cls.clerk = new_test_user(
            cls.env,
            login="forged_admission_clerk",
            groups="base.group_user,account.group_account_invoice",
        )

    def _bill(self):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_b.id,
                "invoice_date": "2026-09-01",
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

    def _context(self, bill):
        return {
            "active_model": "account.move",
            "active_ids": bill.ids,
            "approval_binding_admitted": [["account.move", "post", bill.ids]],
        }

    def test_the_wizard_refuses_a_forged_admission(self):
        bill = self._bill()
        wizard = (
            self.env["wizard.account.move.post"]
            .with_user(self.clerk)
            .with_context(**self._context(bill))
            .create({"move_ids": [Command.set(bill.ids)]})
        )
        with self.assertRaises(UserError):
            wizard.action_post_moves()
        self.assertEqual(bill.state, "draft")

    def _call(self, route, model, method, args, context):
        return self.url_open(
            f"/web/dataset/{route}/{model}/{method}",
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

    def test_a_browser_call_with_a_forged_admission_posts_nothing(self):
        bill = self._bill()
        self.authenticate(self.clerk.login, self.clerk.login)
        context = self._context(bill)
        created = self._call(
            "call_kw",
            "wizard.account.move.post",
            "create",
            [{"move_ids": [[6, 0, bill.ids]]}],
            context,
        )
        posted = self._call(
            "call_button",
            "wizard.account.move.post",
            "action_post_moves",
            [[created["result"]]],
            context,
        )
        self.assertIn("error", posted)
        bill.invalidate_recordset()
        self.assertEqual(bill.state, "draft")
        self.assertFalse(bill.approval_request_id)
