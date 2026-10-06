from datetime import timedelta

from odoo import Command
from odoo.tests import tagged

from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


@tagged("post_install", "-at_install")
class TestAutoReconcileRegressions(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]

    def _invoice_with_ref(self, ref, amount, move_type="out_invoice"):
        account = (
            self.company_data["default_account_revenue"]
            if move_type == "out_invoice"
            else self.company_data["default_account_expense"]
        )
        invoice = self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": self.partner_a.id,
                "ref": ref,
                "invoice_date": "2019-01-01",
                "date": "2019-01-01",
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "l",
                            "quantity": 1,
                            "price_unit": amount,
                            "account_id": account.id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice

    def test_overlapping_references_do_not_crash(self):
        refs = ["AAAAAAAA", "BBBAAAAAAAA", "CCCAAAAAAAA"]
        for ref in refs:
            self._invoice_with_ref(ref, 100.0)
        st_line = self._create_st_line(
            300.0, payment_ref=" ".join(refs), partner_id=self.partner_a.id
        )

        for ref in refs:
            self.assertTrue(
                st_line._is_properly_surrounded(st_line.payment_ref, ref),
                "the test is only meaningful while all three words reach the loop",
            )

        st_line._try_auto_reconcile_statement_lines()
        self.assertTrue(st_line.is_reconciled)

    def test_failing_line_does_not_retire_its_batch(self):
        StatementLine = type(self.env["account.bank.statement.line"])
        genuine = StatementLine._try_auto_reconcile_statement_lines

        def explode(records, *args, **kwargs):
            if len(records) > 1:
                raise ValueError("boom")
            return genuine(records, *args, **kwargs)

        self._invoice_with_ref("ZZZZZZZZZZ", 55.0)
        good = self._create_st_line(
            55.0, payment_ref="PAY ZZZZZZZZZZ", partner_id=self.partner_a.id
        )
        other = self._create_st_line(
            13.0, payment_ref="UNMATCHABLE", partner_id=self.partner_a.id
        )

        self.patch(StatementLine, "_try_auto_reconcile_statement_lines", explode)
        self.env[
            "account.bank.statement.line"
        ]._cron_try_auto_reconcile_statement_lines(batch_size=100)
        self.env.invalidate_all()

        self.assertTrue(
            good.is_reconciled,
            "the batch failed as a whole, so each line is retried alone and this one works",
        )
        self.assertTrue(
            good.line_ids.filtered("reconciled_lines_ids"),
            "the line was stamped as checked without ever being matched",
        )
        self.assertTrue(
            other.cron_last_check,
            "a line the CRON has looked at is marked, matched or not",
        )

    def test_payment_reference_matching_is_sign_symmetric(self):
        def run(move_type, sign, refs):
            for ref in refs:
                self._invoice_with_ref(ref, 100.0, move_type=move_type)
            self._invoice_with_ref("UNRELATEDREF", 77.0, move_type=move_type)
            st_line = self._create_st_line(
                sign * 200.0,
                payment_ref="PAYMENT %s AND %s" % tuple(refs),
                partner_id=self.partner_a.id,
            )
            st_line._try_auto_reconcile_statement_lines()
            return len(st_line.line_ids.filtered("reconciled_lines_ids"))

        inbound = run("out_invoice", 1, ["INVREFAAA", "INVREFBBB"])
        outbound = run("in_invoice", -1, ["BILLREFAAA", "BILLREFBBB"])
        self.assertEqual(inbound, 2, "both invoices are named in the label")
        self.assertEqual(
            outbound, inbound, "the outbound mirror must match the same number of lines"
        )

    def test_import_does_not_retire_unrelated_lines(self):
        existing = self.env["account.bank.statement.line"]
        for index in range(3):
            existing |= self._create_st_line(
                -5.0, payment_ref="PREEXISTING %s" % index, update_create_date=False
            )

        self.env["account.bank.statement.line"].with_context(
            auto_statement_processing=True
        ).create(
            [
                {
                    "journal_id": self.bank_journal.id,
                    "payment_ref": "IMPORT %s" % index,
                    "amount": -7.0,
                    "date": "2019-01-01",
                }
                for index in range(5)
            ]
        )

        self.assertFalse(
            existing.filtered("cron_last_check"),
            "the import retired statement lines it was never given",
        )

    def _run_on_demand(self, from_date="2019-01-01", to_date="2019-12-31"):
        wizard = self.env["wizard.account.bank.statement.line.reconcile.auto"].create(
            {
                "journal_id": self.bank_journal.id,
                "from_date": from_date,
                "to_date": to_date,
            }
        )
        return wizard.action_auto_reconcile()

    def _run_cron(self):
        self.env[
            "account.bank.statement.line"
        ]._cron_try_auto_reconcile_statement_lines(batch_size=100)
        self.env.invalidate_all()

    def _backdate_last_check(self, st_lines, days=1):
        st_lines.cron_last_check = self.env.cr.now() - timedelta(days=days)

    def test_cron_revisits_an_open_line_once_its_document_is_booked(self):
        """The bill is usually booked after the bank movement it settles.

        A run that looked at the transaction on import found nothing to match;
        the next run finds the document booked in between.
        """
        st_line = self._create_st_line(
            42.0,
            payment_ref="PAY BOOKEDLATER",
            partner_id=self.partner_a.id,
            update_create_date=False,
        )
        self._run_cron()
        self.assertFalse(st_line.is_reconciled)
        self.assertTrue(st_line.cron_last_check)
        self._backdate_last_check(st_line)

        self._invoice_with_ref("BOOKEDLATER", 42.0)
        self._run_cron()

        self.assertTrue(
            st_line.is_reconciled,
            "a later run must reach a transaction an earlier run left open",
        )

    def test_cron_visits_each_line_once_per_run(self):
        StatementLine = type(self.env["account.bank.statement.line"])
        genuine = StatementLine._try_auto_reconcile_statement_lines
        visits = []

        def record_visit(records, *args, **kwargs):
            visits.extend(records.ids)
            return genuine(records, *args, **kwargs)

        st_lines = self.env["account.bank.statement.line"]
        for index in range(3):
            st_lines |= self._create_st_line(
                -5.0, payment_ref="NOTHING %s" % index, update_create_date=False
            )
        self._backdate_last_check(st_lines)

        self.patch(StatementLine, "_try_auto_reconcile_statement_lines", record_visit)
        st_lines._cron_try_auto_reconcile_statement_lines(batch_size=1)

        self.assertEqual(
            sorted(visits),
            st_lines.ids,
            "a line stamped by this run must not be offered to it again",
        )

    def test_cron_leaves_alone_a_checked_line_past_the_retry_window(self):
        self._invoice_with_ref("TOOLATEAAA", 42.0)
        st_line = self._create_st_line(
            42.0, payment_ref="PAY TOOLATEAAA", partner_id=self.partner_a.id
        )
        self._backdate_last_check(st_line)

        self._run_cron()

        self.assertFalse(
            st_line.is_reconciled,
            "a transaction imported before the retry window is a person's to settle",
        )

    def test_retry_window_follows_its_setting(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "account.bank_rec_retry_days", "3650"
        )
        self._invoice_with_ref("WIDERWINDOW", 42.0)
        st_line = self._create_st_line(
            42.0, payment_ref="PAY WIDERWINDOW", partner_id=self.partner_a.id
        )
        self.env.cr.execute(
            "UPDATE account_bank_statement_line SET create_date = %s WHERE id = %s",
            (self.env.cr.now() - timedelta(days=400), st_line.id),
        )
        self._backdate_last_check(st_line)

        self._run_cron()

        self.assertTrue(st_line.is_reconciled)

    def _wake_ups(self):
        cron = self.env.ref("account.auto_reconcile_bank_statement_line")
        return (
            self.env["ir.cron.trigger"].sudo().search_count([("cron_id", "=", cron.id)])
        )

    def test_posting_a_document_wakes_the_cron(self):
        before = self._wake_ups()

        self._invoice_with_ref("WAKEUPAAAA", 10.0)
        self.assertEqual(self._wake_ups(), before + 1, "a receivable was posted")

        self._invoice_with_ref("WAKEUPBBBB", 10.0, move_type="in_invoice")
        self.assertEqual(self._wake_ups(), before + 2, "a payable was posted")

    def test_posting_a_transaction_or_a_plain_entry_does_not_wake_the_cron(self):
        before = self._wake_ups()

        self._create_st_line(15.0, payment_ref="NO DOCUMENT HERE")
        self.env["account.move"].create(
            {
                "move_type": "entry",
                "date": "2019-01-01",
                "line_ids": [
                    Command.create(
                        {
                            "name": "accrual",
                            "account_id": self.company_data[
                                "default_account_expense"
                            ].id,
                            "debit": 30.0,
                        }
                    ),
                    Command.create(
                        {
                            "name": "accrual",
                            "account_id": self.company_data[
                                "default_account_revenue"
                            ].id,
                            "credit": 30.0,
                        }
                    ),
                ],
            }
        ).action_post()

        self.assertEqual(
            self._wake_ups(),
            before,
            "neither carries a receivable or payable a transaction could settle",
        )

    def test_on_demand_auto_reconcile_reaches_lines_past_the_retry_window(self):
        """The whole point of the on-demand run.

        `_cron_try_auto_reconcile_statement_lines` revisits a transaction only
        while it is younger than the retry window, so a reconciliation model
        written long after the fact is never applied to an older one. The
        wizard searches by journal and date instead, so that line is reachable
        again.
        """
        self._invoice_with_ref("LATERULEAAA", 42.0)
        st_line = self._create_st_line(
            42.0, payment_ref="PAY LATERULEAAA", partner_id=self.partner_a.id
        )
        self._backdate_last_check(st_line)

        self._run_cron()
        self.assertFalse(
            st_line.is_reconciled,
            "the cron leaves a checked line alone once it is past the retry window",
        )

        self._run_on_demand()
        self.env.invalidate_all()

        self.assertTrue(
            st_line.is_reconciled,
            "the on-demand run searches by journal and date, not by cron_last_check",
        )

    def test_on_demand_auto_reconcile_isolates_a_failing_line_without_retiring_it(self):
        """One bad transaction costs one transaction, and stays in the cron's queue.

        `_try_auto_reconcile_statement_lines` works on the whole recordset and
        aborts on the first line that raises, which is why the cron retries line
        by line. The on-demand run shares that protection but must not stamp
        `cron_last_check`: an ad-hoc pass that happened to hit a bad line must
        not push it to the back of the cron's queue.
        """
        StatementLine = type(self.env["account.bank.statement.line"])
        genuine = StatementLine._try_auto_reconcile_statement_lines

        self._invoice_with_ref("GOODREFAAAA", 55.0)
        good = self._create_st_line(
            55.0, payment_ref="PAY GOODREFAAAA", partner_id=self.partner_a.id
        )
        bad = self._create_st_line(
            13.0, payment_ref="EXPLODE", partner_id=self.partner_a.id
        )

        def explode(records, *args, **kwargs):
            if "EXPLODE" in records.mapped("payment_ref"):
                raise ValueError("boom")
            return genuine(records, *args, **kwargs)

        self.patch(StatementLine, "_try_auto_reconcile_statement_lines", explode)
        self._run_on_demand()
        self.env.invalidate_all()

        self.assertTrue(
            good.is_reconciled,
            "the failing line is isolated in its own savepoint, so this one still runs",
        )
        self.assertFalse(
            bad.cron_last_check,
            "an on-demand run does not stamp a line on the cron's behalf",
        )

    def test_on_demand_auto_reconcile_wizard_defaults_resolve(self):
        """The dialog opens on a one-month window; a raising default breaks it for everyone."""
        defaults = self.env[
            "wizard.account.bank.statement.line.reconcile.auto"
        ].default_get(["company_id", "from_date", "to_date"])
        self.assertEqual(defaults["company_id"], self.env.company.id)
        self.assertLess(defaults["from_date"], defaults["to_date"])
