from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests.common import tagged

from .common import AutomationAccountCommon


@tagged("post_install", "-at_install")
class TestReconcileOpenInvoices(AutomationAccountCommon):
    def setUp(self):
        super().setUp()
        self.step = self._make_step("pass")
        self.runtime = self._make_runtime()
        self.line = self.runtime.line_ids

    def _make_move(self, amount, date, move_type="out_invoice", **vals):
        move = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner.id,
                "journal_id": self.journal_sale.id,
                "invoice_date": date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Open item",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": self.account_income.id,
                            "tax_ids": [],
                        },
                    ),
                ],
                **vals,
            },
        )
        if vals.get("state") != "draft":
            move.action_post()
        return move

    def _apply(self, refund):
        return self.step.reconcile_move_with_open_invoices(self.line, refund)

    def test_the_oldest_invoices_absorb_the_credit_first(self):
        newest = self._make_move(100.0, "2026-08-22")
        oldest = self._make_move(100.0, "2026-08-20")
        middle = self._make_move(100.0, "2026-08-21")
        refund = self._make_move(150.0, "2026-08-25", move_type="out_refund")

        applied = self._apply(refund)

        self.assertEqual(applied, oldest | middle)
        self.assertEqual(oldest.amount_residual, 0.0)
        self.assertEqual(middle.amount_residual, 50.0)
        self.assertEqual(newest.amount_residual, 100.0)
        self.assertEqual(refund.amount_residual, 0.0)

    def test_the_order_is_the_invoice_date_not_the_due_date(self):
        due_later = self._make_move(
            100.0,
            "2026-08-20",
            invoice_payment_term_id=False,
            invoice_date_due="2026-11-18",
        )
        due_sooner = self._make_move(
            100.0,
            "2026-08-21",
            invoice_payment_term_id=False,
            invoice_date_due="2026-09-01",
        )
        refund = self._make_move(100.0, "2026-08-25", move_type="out_refund")

        applied = self._apply(refund)

        self.assertEqual(applied, due_later)
        self.assertEqual(due_later.amount_residual, 0.0)
        self.assertEqual(due_sooner.amount_residual, 100.0)

    def test_invoices_of_one_date_are_taken_by_number(self):
        first = self._make_move(
            100.0,
            "2026-08-20",
            invoice_payment_term_id=False,
            invoice_date_due="2026-11-18",
        )
        second = self._make_move(
            100.0,
            "2026-08-20",
            invoice_payment_term_id=False,
            invoice_date_due="2026-08-20",
        )
        refund = self._make_move(100.0, "2026-08-25", move_type="out_refund")

        applied = self._apply(refund)

        self.assertLess(first.name, second.name)
        self.assertEqual(applied, first)
        self.assertEqual(second.amount_residual, 100.0)

    def test_what_the_invoices_do_not_absorb_stays_as_open_credit(self):
        invoice = self._make_move(100.0, "2026-08-20")
        refund = self._make_move(250.0, "2026-08-25", move_type="out_refund")

        applied = self._apply(refund)

        self.assertEqual(applied, invoice)
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(refund.amount_residual, 150.0)

    def test_a_credit_note_already_applied_is_left_alone(self):
        invoice = self._make_move(100.0, "2026-08-20")
        untouched = self._make_move(100.0, "2026-08-21")
        refund = self._make_move(100.0, "2026-08-25", move_type="out_refund")
        self._apply(refund)

        applied = self._apply(refund)

        self.assertFalse(applied)
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(untouched.amount_residual, 100.0)

    def test_only_the_partner_posted_invoices_are_candidates(self):
        other_partner = self._make_move(
            100.0, "2026-08-18", partner_id=self.third_party.id
        )
        draft = self._make_move(100.0, "2026-08-19", state="draft")
        older_refund = self._make_move(40.0, "2026-08-19", move_type="out_refund")
        invoice = self._make_move(100.0, "2026-08-20")
        refund = self._make_move(100.0, "2026-08-25", move_type="out_refund")

        applied = self._apply(refund)

        self.assertEqual(applied, invoice)
        self.assertEqual(other_partner.amount_residual, 100.0)
        self.assertEqual(draft.state, "draft")
        self.assertEqual(older_refund.amount_residual, 40.0)

    def test_a_move_that_is_not_a_posted_credit_note_is_refused(self):
        invoice = self._make_move(100.0, "2026-08-20")
        draft_refund = self._make_move(
            100.0, "2026-08-25", move_type="out_refund", state="draft"
        )

        with self.assertRaises(UserError):
            self._apply(invoice)
        with self.assertRaises(UserError):
            self._apply(draft_refund)

    def test_the_step_applies_the_credit_note_of_its_predecessor(self):
        invoice = self._make_move(100.0, "2026-08-20")
        refund = self._make_move(100.0, "2026-08-25", move_type="out_refund")
        automation = self.env["automation.rule"].create(
            {
                "name": "TEST - Credit note workflow",
                "model_id": self.model_line.id,
                "trigger": "on_hand",
            },
        )
        self._make_chain(
            [
                "pass",
                "server_action.reconcile_latest_move_with_open_invoices(record)",
            ],
            automation=automation,
        )
        runtime = self._make_runtime(automation=automation)
        first, last = runtime.line_ids.sorted("sequence")
        first.created_record_ref = f"account.move,{refund.id}"

        runtime.action_next_step()
        runtime.action_next_step()

        self.assertEqual(last.state, "done")
        self.assertEqual(runtime.state, "done")
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertEqual(refund.amount_residual, 0.0)

    def test_a_step_with_no_credit_note_behind_it_is_refused(self):
        with self.assertRaises(UserError):
            self.step.reconcile_latest_move_with_open_invoices(self.line)
