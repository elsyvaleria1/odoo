from odoo.fields import Command
from odoo.tests.common import tagged
from odoo.tools import mute_logger

from .test_typed_steps import LINE_LOGGER, TypedStepCase


@tagged("post_install", "-at_install")
class TestApplyAgainst(TypedStepCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.account_expense = cls.env["account.account"].create(
            {
                "name": "Automation Expense",
                "code": "TAAC500",
                "account_type": "expense",
                "company_ids": [Command.link(cls.company.id)],
            },
        )
        cls.journal_purchase = cls._make_journal("purchase", "TAAPU")
        cls.template_bill = cls._vendor_template("in_invoice")
        cls.template_vendor_refund = cls._vendor_template("in_refund")

    @classmethod
    def _vendor_template(cls, move_type):
        return cls.env["account.move.template"].create(
            {
                "name": f"TEST - Vendor {move_type}",
                "journal_code": cls.journal_purchase.code,
                "move_type": move_type,
                "invoice_payment_term_id": cls.immediate.id,
                "line_ids": [
                    Command.create(
                        {
                            "name": "Vendor Item",
                            "account_code": cls.account_expense.code,
                            "sequence": 10,
                            "price_unit": 100.0,
                        },
                    ),
                ],
            },
        )

    def _open_bill(self, date):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner.id,
                "journal_id": self.journal_purchase.id,
                "invoice_date": date,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "Older bill",
                            "quantity": 1,
                            "price_unit": 100.0,
                            "account_id": self.account_expense.id,
                            "tax_ids": [],
                        },
                    ),
                ],
            },
        )
        bill.action_post()
        return bill

    def _bill_refund_apply(self, **bill_vals):
        bill = self._document_step(self.template_bill, name="Bill", **bill_vals)
        refund = self._document_step(
            self.template_vendor_refund,
            name="Refund",
            predecessors=bill,
        )
        apply = self._typed_step(
            "workflow_apply_credit_note",
            name="Apply",
            predecessors=refund,
            workflow_target_step_id=bill.id,
        )
        return bill, refund, apply

    def test_the_refund_settles_the_bill_of_its_run_not_an_older_one(self):
        older = self._open_bill("2026-07-01")
        bill, refund, apply = self._bill_refund_apply()
        runtime = self._make_runtime()

        runtime.action_run_all()

        run_bill = self._line(runtime, bill).created_record_ref
        run_refund = self._line(runtime, refund).created_record_ref
        # Oldest first would hand the refund to the older bill.
        self.assertLess(older.date, run_bill.date)
        self.assertEqual(self._line(runtime, apply).state, "done")
        self.assertEqual(runtime.state, "done")
        self.assertEqual(run_bill.amount_residual, 0.0)
        self.assertEqual(run_refund.amount_residual, 0.0)
        self.assertEqual(older.amount_residual, 100.0)
        self.assertEqual(
            self._line(runtime, apply).output["invoices"],
            [run_bill.name],
        )

    @mute_logger(LINE_LOGGER)
    def test_a_draft_bill_stops_the_step_until_it_is_posted_and_retried(self):
        bill, refund, apply = self._bill_refund_apply(workflow_auto_post=False)
        runtime = self._make_runtime()

        runtime.action_run_all()

        run_bill = self._line(runtime, bill).created_record_ref
        run_refund = self._line(runtime, refund).created_record_ref
        self.assertEqual(runtime.state, "error")
        self.assertEqual(self._line(runtime, apply).state, "error")
        self.assertIn("posted", self._line(runtime, apply).error_message)
        self.assertEqual(run_bill.state, "draft")
        self.assertEqual(run_refund.amount_residual, 100.0)

        run_bill.action_post()
        runtime.action_retry()

        self.assertEqual(self._line(runtime, apply).state, "done")
        self.assertEqual(run_bill.amount_residual, 0.0)
        self.assertEqual(run_refund.amount_residual, 0.0)

    @mute_logger(LINE_LOGGER)
    def test_a_bill_of_another_partner_is_refused(self):
        bill, refund, apply = self._bill_refund_apply(
            workflow_partner_source="third_party",
        )
        runtime = self._make_runtime(third_party_id=self.third_party.id)

        runtime.action_run_all()

        self.assertEqual(self._line(runtime, apply).state, "error")
        self.assertIn("nothing open", self._line(runtime, apply).error_message)
        self.assertEqual(
            self._line(runtime, bill).created_record_ref.amount_residual,
            100.0,
        )
        self.assertEqual(
            self._line(runtime, refund).created_record_ref.amount_residual,
            100.0,
        )

    def test_apply_against_must_name_a_document_step_upstream(self):
        bill, _refund, apply = self._bill_refund_apply()
        other = self._document_step(self.template_bill, name="Other")
        self.assertFalse(self.automation._get_step_reference_problems())

        apply.workflow_target_step_id = other

        problems = self.automation._get_step_reference_problems()
        self.assertRegex(problems[0], "'Other'.*not upstream")

        apply.workflow_target_step_id = self._typed_step(
            "workflow_reconcile_statement",
            name="Settle",
            predecessors=bill,
        )

        problems = self.automation._get_step_reference_problems()
        self.assertTrue(any("'Settle', which makes none" in p for p in problems))
