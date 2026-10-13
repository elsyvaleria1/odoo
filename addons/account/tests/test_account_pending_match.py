from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import SQL

from odoo.addons.account.models.account_move import AccountMove
from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


class PendingMatchCommon(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        config = cls.company.account_config_id
        config.tax_exigibility = True
        config.account_cash_basis_base_account_id = cls.env["account.account"].create(
            {"code": "CABA.BASE", "name": "Cash basis base", "account_type": "income"}
        )
        cls.transition_account = cls.env["account.account"].create(
            {
                "code": "CABA.TRANS",
                "name": "Tax to settle",
                "account_type": "asset_current",
                "reconcile": True,
            }
        )
        cls.tax_account = cls.env["account.account"].create(
            {"code": "CABA.TAX", "name": "Tax paid", "account_type": "asset_current"}
        )
        plan = cls.env["account.analytic.plan"].create({"name": "Pending match plan"})
        cls.cost_center = cls.env["account.analytic.account"].create(
            {"name": "CC1", "plan_id": plan.id}
        )
        repartition = [
            Command.create({"repartition_type": "base"}),
            Command.create(
                {"repartition_type": "tax", "account_id": cls.tax_account.id}
            ),
        ]
        cls.caba_tax = cls.env["account.tax"].create(
            {
                "name": "VAT 16% on payment",
                "amount": 16.0,
                "type_tax_use": "purchase",
                "tax_exigibility": "on_payment",
                "analytic": True,
                "cash_basis_transition_account_id": cls.transition_account.id,
                "invoice_repartition_line_ids": repartition,
                "refund_repartition_line_ids": repartition,
            }
        )

    def _draft(self, amount, move_type="in_invoice", taxes=None, **kwargs):
        account = (
            self.company_data["default_account_expense"]
            if move_type.startswith("in_")
            else self.company_data["default_account_revenue"]
        )
        line = {
            "name": "pending",
            "quantity": 1.0,
            "price_unit": amount,
            "account_id": account.id,
            "tax_ids": [Command.set(taxes.ids if taxes else [])],
        }
        if kwargs.pop("analytic", False):
            line["analytic_distribution"] = {str(self.cost_center.id): 100.0}
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-05",
                "date": "2019-01-05",
                "invoice_line_ids": [Command.create(line)],
                **kwargs,
            }
        )

    def _term(self, move):
        return move.line_ids.filtered(
            lambda line: (
                line.account_id.account_type
                in ("asset_receivable", "liability_payable")
            )
        )

    def _match_on_bank(self, move, amount=None, date="2019-01-03"):
        sign = 1 if move.is_inbound() else -1
        st_line = self._create_st_line(
            sign * (amount or move.amount_total),
            date=date,
            partner_id=move.partner_id.id,
        )
        st_line.set_line_bank_statement_line(self._term(move).ids)
        return st_line

    def _caba_moves(self, move):
        return self.env["account.move"].search(
            [("tax_cash_basis_origin_move_id", "=", move.id)]
        )

    def _posted_balance(self, account):
        lines = self.env["account.move.line"].search(
            [("account_id", "=", account.id), ("parent_state", "=", "posted")]
        )
        return sum(lines.mapped("balance"))


@tagged("post_install", "-at_install")
class TestAccountPendingMatch(PendingMatchCommon):
    def test_a_bank_match_with_a_draft_is_a_pending_match(self):
        bill = self._draft(1000.0)

        st_line = self._match_on_bank(bill)

        self.assertTrue(st_line.is_reconciled, "the transaction leaves the queue")
        self.assertEqual(bill.state, "draft")
        self.assertEqual(bill.payment_state, "not_paid")
        self.assertFalse(self._term(bill).matched_debit_ids)
        self.assertRecordValues(
            bill.pending_match_ids,
            [
                {
                    "amount": 1000.0,
                    "origin": "bank_manual",
                    "posted_move_id": st_line.move_id.id,
                }
            ],
        )
        self.assertEqual(bill.pending_payment_amount, 1000.0)
        self.assertEqual(
            st_line.line_ids.filtered("pending_match_amount").pending_match_label,
            f"{bill.display_name} (pending posting)",
        )

    def test_reconciling_a_draft_raises(self):
        bill = self._draft(100.0)
        payment = self._draft(100.0, move_type="in_refund")
        payment.action_post()

        with self.assertRaisesRegex(UserError, "only reconcile posted entries"):
            (self._term(bill) + self._term(payment)).reconcile()

    def test_drafts_cannot_match_each_other(self):
        bill = self._draft(100.0)
        refund = self._draft(100.0, move_type="in_refund")

        with self.assertRaises(UserError):
            (self._term(bill) + self._term(refund)).reconcile()
        self.assertEqual(bill.payment_state, "not_paid")
        self.assertEqual(refund.payment_state, "not_paid")

    def test_posting_the_draft_completes_the_match_once(self):
        invoice = self._draft(500.0, move_type="out_invoice")
        calls = []
        original = AccountMove._invoice_paid_hook

        def spy(moves):
            calls.extend((move.id, move.state) for move in moves)
            return original(moves)

        with patch.object(AccountMove, "_invoice_paid_hook", spy):
            self._match_on_bank(invoice)
            self.assertEqual(calls, [], "a draft is paid by nothing")
            invoice.action_post()

        self.assertEqual(calls, [(invoice.id, "posted")])
        self.assertTrue(self._term(invoice).reconciled)
        self.assertEqual(invoice.payment_state, "paid")
        self.assertFalse(invoice.pending_match_ids)

    def test_posting_completes_the_match_up_to_its_amount(self):
        advance = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-02",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_payable"
                            ].id,
                            "partner_id": self.partner_a.id,
                            "debit": 1000.0,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "credit": 1000.0,
                        }
                    ),
                ],
            }
        )
        advance.action_post()
        advance_line = self._term(advance)
        bill = self._draft(400.0)

        bill.js_add_outstanding_line(advance_line.id)
        self.assertRecordValues(
            bill.pending_match_ids, [{"amount": 400.0, "origin": "outstanding"}]
        )
        bill.invoice_line_ids.price_unit = 700.0
        bill.action_post()

        self.assertEqual(bill.amount_residual, 300.0)
        self.assertEqual(advance_line.amount_residual, 600.0)
        self.assertEqual(bill.payment_state, "partial")

    def test_a_committed_line_is_not_offered_twice(self):
        bill = self._draft(800.0)
        st_line = self._match_on_bank(bill)
        posted_bill = self._draft(800.0)
        posted_bill.action_post()

        widget = posted_bill.invoice_outstanding_credits_debits_widget
        offered = [entry["id"] for entry in (widget or {}).get("content", [])]
        committed = st_line.line_ids.filtered("pending_match_amount")
        self.assertTrue(committed)
        self.assertNotIn(committed.id, offered)

    def test_posting_under_a_locked_tax_period(self):
        bill = self._draft(1000.0, taxes=self.caba_tax)
        self._match_on_bank(bill)
        self.company.account_config_id.tax_lock_date = "2019-01-31"

        bill.action_post()

        caba = self._caba_moves(bill)
        self.assertEqual(caba.mapped("state"), ["posted"])
        self.assertGreater(caba.date, fields.Date.to_date("2019-01-31"))
        self.assertTrue(self._term(bill).reconciled)

    def test_the_cash_basis_entry_of_a_posted_draft_carries_analytics(self):
        bill = self._draft(1000.0, taxes=self.caba_tax, analytic=True)
        self._match_on_bank(bill)

        bill.action_post()

        caba = self._caba_moves(bill)
        self.assertTrue(caba)
        self.assertTrue(
            caba.line_ids.analytic_line_ids,
            "a cash-basis entry posted with its bill goes through the same pipeline",
        )

    def test_reset_to_draft_reverses_cash_basis_and_keeps_the_match(self):
        bill = self._draft(1000.0, taxes=self.caba_tax)
        bill.action_post()
        st_line = self._match_on_bank(bill)
        self.assertEqual(self._posted_balance(self.tax_account), 160.0)

        bill.action_draft()

        self.assertEqual(self._posted_balance(self.tax_account), 0.0)
        self.assertFalse(self._term(bill).matched_debit_ids)
        self.assertRecordValues(
            bill.pending_match_ids, [{"amount": 1160.0, "origin": "reset_to_draft"}]
        )
        self.assertTrue(st_line.is_reconciled)

        bill.action_post()
        self.assertTrue(self._term(bill).reconciled)
        self.assertEqual(self._posted_balance(self.tax_account), 160.0)

    def test_resetting_the_bank_entry_leaves_no_draft_partial(self):
        bill = self._draft(300.0)
        bill.action_post()
        st_line = self._match_on_bank(bill)

        st_line.move_id.action_draft()

        self.assertFalse(self._term(bill).matched_debit_ids)
        self.assertEqual(bill.payment_state, "not_paid")
        self.assertEqual(
            self.env["account.pending.match"]
            .search([("posted_line_id", "in", self._term(bill).ids)])
            .origin,
            "reset_to_draft",
        )
        st_line.move_id.action_post()
        self.assertTrue(self._term(bill).reconciled)

    def _assert_back_in_queue(self, st_line, bill):
        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(st_line.line_ids.filtered("pending_match_amount"))
        self.assertTrue(
            any(
                "dropped" in (message.body or "")
                for message in st_line.move_id.message_ids
            )
        )
        if bill.exists():
            self.assertFalse(bill.pending_match_ids)
            self.assertTrue(
                any("dropped" in (message.body or "") for message in bill.message_ids)
            )

    def test_a_cancelled_draft_sends_the_transaction_back(self):
        bill = self._draft(250.0)
        st_line = self._match_on_bank(bill)

        bill.action_cancel()

        self._assert_back_in_queue(st_line, bill)

    def test_a_deleted_draft_sends_the_transaction_back(self):
        bill = self._draft(250.0)
        st_line = self._match_on_bank(bill)

        bill.unlink()

        self._assert_back_in_queue(st_line, bill)

    def test_a_draft_of_another_partner_sends_the_transaction_back(self):
        bill = self._draft(250.0)
        st_line = self._match_on_bank(bill)

        bill.partner_id = self.partner_b

        self._assert_back_in_queue(st_line, bill)

    def test_resetting_a_move_matched_with_a_partnerless_item_releases_it(self):
        invoice = self.init_invoice(
            "out_invoice", invoice_date="2019-01-01", amounts=[100.0], post=True
        )
        receivable = invoice.line_ids.filtered(
            lambda line: line.display_type == "payment_term"
        )
        collection = self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-05",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": receivable.account_id.id,
                            "balance": -receivable.balance,
                        }
                    ),
                    Command.create(
                        {
                            "account_id": self.company_data[
                                "default_journal_bank"
                            ].default_account_id.id,
                            "balance": receivable.balance,
                        }
                    ),
                ],
            }
        )
        collection.action_post()
        collected = collection.line_ids.filtered(
            lambda line: line.account_id == receivable.account_id
        )
        self.assertFalse(collected.partner_id)
        (receivable + collected).reconcile()

        invoice.action_draft()

        self.assertFalse(
            self.env["account.pending.match"].search(
                [("posted_line_id", "=", collected.id)]
            )
        )
        self.assertEqual(collected.amount_residual, -receivable.balance)

    def test_a_draft_below_its_match_sends_the_transaction_back(self):
        bill = self._draft(250.0)
        st_line = self._match_on_bank(bill)

        bill.invoice_line_ids.price_unit = 200.0

        self._assert_back_in_queue(st_line, bill)

    def test_a_draft_above_its_match_keeps_it(self):
        bill = self._draft(250.0)
        st_line = self._match_on_bank(bill)

        bill.invoice_line_ids.price_unit = 300.0
        bill.invoice_date = "2019-01-10"

        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(bill.pending_payment_amount, 250.0)
        bill.action_post()
        self.assertEqual(bill.amount_residual, 50.0)

    def test_automation_proposes_and_a_person_confirms(self):
        bill = self._draft(31250.4)
        st_line = self._create_st_line(-31250.4, payment_ref="SPEI ENVIADO 0010")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(bill.pending_match_ids, "automation matches nothing itself")
        self.assertEqual(st_line.draft_match_proposal_ids, self._term(bill))
        self.assertEqual(st_line.draft_match_proposal_label, bill.display_name)

        st_line.action_confirm_draft_match_proposal()

        self.assertTrue(st_line.is_reconciled)
        self.assertRecordValues(bill.pending_match_ids, [{"origin": "bank_auto"}])
        self.assertEqual(bill.state, "draft")
        self.assertFalse(st_line.draft_match_proposal_label)

    def test_a_dismissed_proposal_is_forgotten(self):
        self._draft(31250.4)
        st_line = self._create_st_line(-31250.4, payment_ref="SPEI ENVIADO 0011")
        st_line._try_auto_reconcile_statement_lines()

        st_line.action_dismiss_draft_match_proposal()

        self.assertFalse(st_line.draft_match_proposal_ids)
        self.assertFalse(st_line.is_reconciled)

    def _imported_bill(self, amount):
        bill = self._draft(amount)
        bill.invoice_line_ids.with_context(
            skip_is_manually_modified=True
        ).is_imported = True
        return bill

    def test_a_clean_import_posts_on_its_match(self):
        self.company.account_config_id.autopost_bills = True
        self.partner_a.autopost_bills = "ask"
        bill = self._imported_bill(640.0)
        self.assertTrue(bill._is_clean_import())

        self._match_on_bank(bill)

        self.assertEqual(bill.state, "posted")
        self.assertTrue(self._term(bill).reconciled)
        self.assertFalse(bill.pending_match_ids)

    def test_a_bill_waits_when_its_partner_never_autoposts(self):
        self.company.account_config_id.autopost_bills = True
        self.partner_a.autopost_bills = "never"
        bill = self._imported_bill(640.0)

        self._match_on_bank(bill)

        self.assertEqual(bill.state, "draft")
        self.assertTrue(bill.pending_match_ids)

    def test_a_bill_typed_by_a_person_waits(self):
        self.company.account_config_id.autopost_bills = True
        self.partner_a.autopost_bills = "always"
        bill = self._draft(640.0)

        self._match_on_bank(bill)

        self.assertEqual(bill.state, "draft")
        self.assertTrue(bill.pending_match_ids)

    def test_a_payment_registered_on_a_draft_is_pending(self):
        bill = self._draft(420.0)

        payment = (
            self.env["wizard.account.move.line.pay"]
            .with_context(active_model="account.move", active_ids=bill.ids)
            .create({"payment_date": "2019-01-06"})
            ._create_payments()
        )

        self.assertEqual(bill.payment_state, "not_paid")
        if payment.move_id:
            self.assertRecordValues(
                bill.pending_match_ids, [{"origin": "register_payment"}]
            )
            bill.action_post()
            self.assertIn(bill.payment_state, ("paid", "in_payment"))

    def test_partials_only_ever_join_posted_items(self):
        bill = self._draft(100.0, taxes=self.caba_tax)
        self._match_on_bank(bill)
        posted = self._draft(90.0, taxes=self.caba_tax)
        posted.action_post()
        self._match_on_bank(posted)
        posted.action_draft()
        bill.action_post()

        self.env.flush_all()
        self.assertFalse(
            self.env.execute_query(
                SQL(
                    """
                    SELECT partial.id
                      FROM account_partial_reconcile partial
                      JOIN account_move_line line
                        ON line.id IN (partial.debit_move_id, partial.credit_move_id)
                     WHERE line.parent_state != 'posted'
                    """
                )
            )
        )
