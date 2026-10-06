from datetime import date

from odoo.exceptions import AccessError
from odoo.fields import Command
from odoo.tests import freeze_time, tagged

from .common import AccountApprovalCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestPaymentState(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.treasury_user = cls.env["res.users"].create(
            {
                "name": "Treasury",
                "login": "treasury",
                "email": "treasury@test.com",
                "group_ids": [
                    (6, 0, [cls.env.ref("approval_account.group_treasury_payment").id]),
                ],
            },
        )
        cls.plain_user = cls.env["res.users"].create(
            {
                "name": "Plain",
                "login": "plain",
                "email": "plain@test.com",
                "group_ids": [(6, 0, [cls.env.ref("account.group_account_user").id])],
            },
        )
        cls.category = cls.env["approval.category"].create(
            {
                "name": "Payment (payable)",
                "approval_type": "accounting",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
            },
        )
        cls.general_category = cls.env["approval.category"].create(
            {
                "name": "General (not payable)",
                "approval_type": "general",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
            },
        )
        for category in (cls.category, cls.general_category):
            add_category_approver(category, cls.approver, required=True)

    def _new_draft_request(self, category=None, amount=100.0, owner=None):
        vals = {
            "name": "Payment request",
            "category_id": (category or self.category).id,
            "partner_id": self.partner_a.id,
            "amount": amount,
            "date": "2026-06-01",
        }
        if owner is not None:
            vals["request_owner_id"] = owner.id
        return self.env["approval.request"].create(vals)

    def _new_request(self, category=None, amount=100.0, owner=None):
        request = self._new_draft_request(category=category, amount=amount, owner=owner)
        request.action_confirm()
        return request

    def _new_approved_request(self, category=None, amount=100.0, owner=None):
        request = self._new_request(category=category, amount=amount, owner=owner)
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")
        return request

    def test_is_payable_true_for_accounting_positive_amount(self):
        request = self._new_draft_request()
        self.assertTrue(request.is_payable)

    def test_is_payable_false_for_general_category(self):
        request = self._new_draft_request(category=self.general_category)
        self.assertFalse(request.is_payable)

    def test_is_payable_false_for_zero_amount(self):
        request = self._new_draft_request(amount=0.0)
        self.assertFalse(request.is_payable)

    def test_is_payable_recomputes_on_amount_change(self):
        request = self._new_draft_request()
        self.assertTrue(request.is_payable)
        request.amount = 0.0
        self.assertFalse(request.is_payable)

    def test_mark_paid_sets_state_date_user(self):
        request = self._new_approved_request()
        self.treasury_user.tz = "America/Mexico_City"
        # 01:00 UTC is still the previous day in Mexico City: the payment is dated on
        # the treasurer's calendar, not on the server's.
        with freeze_time("2026-09-11 01:00:00"):
            request.with_user(self.treasury_user).action_mark_paid()
        self.assertEqual(request.payment_state, "paid")
        self.assertEqual(request.payment_date, date(2026, 9, 10))
        self.assertEqual(request.paid_by_user_id, self.treasury_user)

    def test_mark_not_paid_clears_fields(self):
        request = self._new_approved_request()
        request.with_user(self.treasury_user).action_mark_paid()
        request.with_user(self.treasury_user).action_mark_not_paid()
        self.assertEqual(request.payment_state, "not_paid")
        self.assertFalse(request.payment_date)
        self.assertFalse(request.paid_by_user_id)

    def test_mark_paid_noop_when_not_approved(self):
        request = self._new_request()
        self.assertEqual(request.state, "pending")
        request.with_user(self.treasury_user).action_mark_paid()
        self.assertEqual(request.payment_state, "not_paid")

    def test_mark_paid_blocked_for_non_treasury_user(self):
        request = self._new_approved_request()
        with self.assertRaises(AccessError):
            request.with_user(self.plain_user).action_mark_paid()

    def test_direct_write_payment_state_blocked_for_non_member(self):
        request = self._new_approved_request(owner=self.plain_user)
        with self.assertRaises(AccessError):
            request.with_user(self.plain_user).write({"payment_state": "paid"})

    def test_direct_write_payment_state_allowed_for_member(self):
        request = self._new_approved_request()
        request.sudo().write({"payment_state": "paid"})
        self.assertEqual(request.payment_state, "paid")

    def test_su_bypasses_payment_field_guard(self):
        request = self._new_approved_request()
        request.with_user(self.plain_user).sudo().write({"payment_state": "paid"})
        self.assertEqual(request.payment_state, "paid")

    def _reconcile_bsl_against_payable(self, bsl, user):
        liquidity_lines = bsl.line_ids.filtered(
            lambda line: (
                line.account_id.account_type in ("asset_cash", "liability_credit_card")
            ),
        )
        suspense_lines = bsl.line_ids - liquidity_lines
        suspense_lines.account_id = self.account_payable

        move = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": bsl.date,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.account_payable.id,
                            "partner_id": self.partner_a.id,
                            "debit": suspense_lines.credit,
                            "credit": suspense_lines.debit,
                        },
                    ),
                    Command.create(
                        {
                            "account_id": self.account_expense.id,
                            "debit": suspense_lines.debit,
                            "credit": suspense_lines.credit,
                        },
                    ),
                ],
            },
        )
        move.action_post()
        payable_line = move.line_ids.filtered(
            lambda line: line.account_id == self.account_payable,
        )
        (suspense_lines + payable_line).with_user(user).reconcile()

    def test_reconciliation_auto_marks_paid_when_treasury_user(self):
        bank_journal = self.company_data["default_journal_bank"]
        bsl = self.env["account.bank.statement.line"].create(
            {
                "journal_id": bank_journal.id,
                "date": "2026-06-01",
                "amount": -100.0,
                "payment_ref": "Payment for request",
                "partner_id": self.partner_a.id,
            },
        )
        request = self._new_approved_request()
        request.sudo().bank_statement_line_id = bsl

        self._reconcile_bsl_against_payable(bsl, self.treasury_user)

        self.assertEqual(request.payment_state, "paid")
        self.assertEqual(request.paid_by_user_id, self.treasury_user)

    def test_reconciliation_marks_paid_whoever_reconciles(self):
        bank_journal = self.company_data["default_journal_bank"]
        bsl = self.env["account.bank.statement.line"].create(
            {
                "journal_id": bank_journal.id,
                "date": "2026-06-01",
                "amount": -100.0,
                "payment_ref": "Payment for request",
                "partner_id": self.partner_a.id,
            },
        )
        request = self._new_approved_request()
        request.sudo().bank_statement_line_id = bsl

        self._reconcile_bsl_against_payable(bsl, self.plain_user)

        self.assertEqual(
            request.payment_state,
            "paid",
            "The payment state follows the bank transaction, not the "
            "privileges of whoever happened to reconcile it",
        )
        self.assertEqual(request.paid_by_user_id, self.plain_user)

    def test_unreconciliation_reverts_payment_state(self):
        bank_journal = self.company_data["default_journal_bank"]
        bsl = self.env["account.bank.statement.line"].create(
            {
                "journal_id": bank_journal.id,
                "date": "2026-06-01",
                "amount": -100.0,
                "payment_ref": "Payment for request",
                "partner_id": self.partner_a.id,
            },
        )
        request = self._new_approved_request()
        request.sudo().bank_statement_line_id = bsl

        self._reconcile_bsl_against_payable(bsl, self.treasury_user)
        self.assertEqual(request.payment_state, "paid")

        bsl.line_ids._all_reconciled_lines().remove_move_reconcile()

        self.assertEqual(
            request.payment_state,
            "not_paid",
            "Undoing the reconciliation has to undo the payment mark",
        )
        self.assertFalse(request.payment_date)
        self.assertFalse(request.paid_by_user_id)

    def test_create_payment_state_blocked_for_non_member(self):
        # The seal has to hold from both sides: write() has always refused,
        # but a request could be created already paid, which reaches the same
        # state without ever passing the gate.
        vals = {
            "name": "Born paid",
            "category_id": self.category.id,
            "partner_id": self.partner_a.id,
            "amount": 100.0,
            "date": "2026-06-01",
            "payment_state": "paid",
        }
        with self.assertRaises(AccessError):
            self.env["approval.request"].with_user(self.plain_user).create(vals)

    def test_create_payment_date_blocked_for_non_member(self):
        vals = {
            "name": "Born stamped",
            "category_id": self.category.id,
            "partner_id": self.partner_a.id,
            "amount": 100.0,
            "date": "2026-06-01",
            "paid_by_user_id": self.plain_user.id,
        }
        with self.assertRaises(AccessError):
            self.env["approval.request"].with_user(self.plain_user).create(vals)

    def test_create_payment_state_allowed_for_member(self):
        request = (
            self.env["approval.request"]
            .with_user(self.treasury_user)
            .create(
                {
                    "name": "Born paid, by treasury",
                    "category_id": self.category.id,
                    "partner_id": self.partner_a.id,
                    "amount": 100.0,
                    "date": "2026-06-01",
                    "payment_state": "paid",
                },
            )
        )
        self.assertEqual(request.payment_state, "paid")

    def test_create_without_payment_fields_is_untouched(self):
        # The gate must not stand in the way of an ordinary request: the
        # fields are absent from vals, so the check never fires.
        request = self._new_draft_request(owner=self.plain_user)
        self.assertEqual(request.payment_state, "not_paid")
