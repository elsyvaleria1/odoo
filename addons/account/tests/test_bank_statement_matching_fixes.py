from unittest.mock import patch

from odoo import Command
from odoo.exceptions import RedirectWarning, ValidationError
from odoo.tests import tagged

from odoo.addons.account.models import (
    account_bank_statement_line_reconcile as reconcile_module,
)
from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon
from odoo.addons.account.tools import structured_reference as sr


@tagged("post_install", "-at_install")
class TestBankStatementMatchingFixes(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.expense = cls.company_data["default_account_expense"]
        cls.jpy = cls.setup_other_currency("JPY", rates=[("1900-01-01", 150.0)])

    def _bill(self, amount, ref):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-01",
                "ref": ref,
                "payment_reference": ref,
                "invoice_line_ids": [
                    Command.create(
                        {
                            "name": "line",
                            "price_unit": amount,
                            "account_id": self.expense.id,
                            "tax_ids": [],
                        }
                    )
                ],
            }
        )
        bill.action_post()
        return bill

    def _payable(self, move):
        return move.line_ids.filtered(
            lambda line: line.account_id.account_type == "liability_payable"
        )

    def _proposal(self, st_line):
        return st_line.move_id.line_ids.filtered(
            lambda line: line.account_id == st_line.journal_id.suspense_account_id
        ).reconcile_model_id

    def _model(self, name, **kw):
        return self.env["account.reconcile.model"].create(
            {
                "name": name,
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.expense.id,
                            "amount_type": "percentage",
                            "amount_string": "100",
                        }
                    )
                ],
                **kw,
            }
        )

    def test_zero_decimal_currency_exchange_difference_is_booked(self):
        receivable = self._create_invoice_line(
            "out_invoice",
            currency_id=self.jpy.id,
            invoice_date="2019-01-01",
            invoice_line_ids=[{"price_unit": 10000.0}],
        )
        self.assertAlmostEqual(receivable.balance, 66.67)
        st_line = self._create_st_line(
            66.40,
            partner_id=self.partner_a.id,
            foreign_currency_id=self.jpy.id,
            amount_currency=10000.0,
        )
        self.assertAlmostEqual(
            st_line._lines_get_account_balance_exchange_diff(
                receivable.currency_id,
                receivable.amount_residual,
                receivable.amount_residual_currency,
            ),
            -0.27,
        )
        st_line.set_line_bank_statement_line(receivable.ids)
        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(receivable.reconciled)
        self.assertRecordValues(
            receivable, [{"amount_residual": 0.0, "amount_residual_currency": 0.0}]
        )
        self.assertTrue(
            (
                receivable.matched_debit_ids | receivable.matched_credit_ids
            ).exchange_move_id
        )

    def test_one_cent_exchange_difference_on_a_full_payment_is_booked(self):
        chf = self.setup_other_currency("CHF", rates=[("1900-01-01", 0.5)])
        suspense = self.bank_journal.suspense_account_id
        for paid, difference in ((200.01, 0.01), (199.99, -0.01)):
            receivable = self._create_invoice_line(
                "out_invoice",
                currency_id=chf.id,
                invoice_date="2019-01-01",
                invoice_line_ids=[{"price_unit": 100.0}],
            )
            self.assertAlmostEqual(receivable.balance, 200.0)
            st_line = self._create_st_line(
                paid,
                partner_id=self.partner_a.id,
                foreign_currency_id=chf.id,
                amount_currency=100.0,
            )
            self.assertAlmostEqual(
                st_line._lines_get_account_balance_exchange_diff(
                    receivable.currency_id,
                    receivable.amount_residual,
                    receivable.amount_residual_currency,
                ),
                difference,
            )
            st_line.set_line_bank_statement_line(receivable.ids)
            self.assertFalse(
                st_line.line_ids.filtered(lambda line: line.account_id == suspense)
            )
            self.assertTrue(receivable.reconciled)
            self.assertTrue(
                (
                    receivable.matched_debit_ids | receivable.matched_credit_ids
                ).exchange_move_id
            )

    def test_bank_fee_model_is_not_proposed_for_every_transaction(self):
        self._model(
            "Fees probe",
            match_journal_ids=self.bank_journal.ids,
            is_bank_fee_model=True,
            trigger="auto_reconcile",
        )
        st_line = self._create_st_line(-25000.0, payment_ref="Salary payroll October")
        st_line._try_auto_reconcile_statement_lines()
        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(self._proposal(st_line))

    def test_reference_named_twice_on_a_document_counts_its_residual_once(self):
        bill_1 = self._bill(100.0, "BILLREF0001")
        bill_2 = self._bill(100.0, "BILLREF0002")
        st_line = self._create_st_line(
            -150.0,
            payment_ref="Paying BILLREF0001 BILLREF0002",
            partner_id=self.partner_a.id,
        )
        st_line._try_auto_reconcile_statement_lines()
        self.assertRecordValues(
            self._payable(bill_1) + self._payable(bill_2),
            [{"amount_residual": 0.0}, {"amount_residual": -50.0}],
        )
        self.assertTrue(st_line.is_reconciled)

    def test_unreviewed_match_does_not_teach_a_partner(self):
        self._bill(777.31, "UNRELATED")
        guessed = self._create_st_line(
            -777.31, payment_ref="wire out", partner_name="QQX TRANSFER NINE"
        )
        guessed._try_auto_reconcile_statement_lines()
        self.assertEqual(guessed.auto_reconcile_rule, "amount_alone")
        self.assertFalse(guessed.checked)

        later = self._create_st_line(
            -12.0, payment_ref="another wire", partner_name="QQX TRANSFER NINE"
        )
        self.assertFalse(later.partner_id)

    def test_reviewed_precedents_teach_a_partner_by_name(self):
        for index in range(2):
            precedent = self._create_st_line(
                -10.0 - index,
                payment_ref=f"rent {index}",
                partner_name="LANDLORD LTD",
                partner_id=self.partner_b.id,
            )
            precedent.set_account_bank_statement_line(
                precedent.line_ids[-1].id, self.expense.id
            )
            precedent.move_id.checked = True
            self.assertTrue(precedent.is_reconciled)

        later = self._create_st_line(
            -12.0, payment_ref="rent later", partner_name="LANDLORD LTD"
        )
        self.assertEqual(later.partner_id, self.partner_b)

    def test_setting_a_partner_across_journals_stays_within_each_journal(self):
        other_journal = self.env["account.journal"].create(
            {"name": "Bank 2", "code": "BNK2", "type": "bank"}
        )

        def line(journal, name):
            return self._create_st_line(10.0, journal_id=journal.id, partner_name=name)

        selected = line(self.bank_journal, "ALPHA NAME") + line(
            other_journal, "BETA NAME"
        )
        same_journal_same_name = line(self.bank_journal, "ALPHA NAME")
        other_journal_same_name = line(other_journal, "ALPHA NAME")

        selected.set_partner_bank_statement_line(self.partner_b.id)

        self.assertEqual(selected.partner_id, self.partner_b)
        self.assertEqual(same_journal_same_name.partner_id, self.partner_b)
        self.assertFalse(other_journal_same_name.partner_id)

    def test_amount_regex_needs_a_capturing_group(self):
        with self.assertRaises(ValidationError):
            self.env["account.reconcile.model"].create(
                {
                    "name": "no group",
                    "line_ids": [
                        Command.create(
                            {
                                "account_id": self.expense.id,
                                "amount_type": "regex",
                                "amount_string": r"FEE \d+",
                            }
                        )
                    ],
                }
            )

    def test_amount_regex_with_an_unmatched_optional_group_warns(self):
        model = self.env["account.reconcile.model"].create(
            {
                "name": "optional group",
                "line_ids": [
                    Command.create(
                        {
                            "account_id": self.expense.id,
                            "amount_type": "regex",
                            "amount_string": r"FEE(?: ([\d.]+))?",
                        }
                    )
                ],
            }
        )
        st_line = self._create_st_line(-30.0, payment_ref="FEE")
        with self.assertRaises(RedirectWarning):
            model._trigger_reconciliation_model(st_line)

    def test_resequencing_models_refreshes_once_and_never_auto_reconciles(self):
        st_line = self._create_st_line(100.0, payment_ref="RESEQPROBE PAYMENT")
        self.env.flush_all()
        manual = self._model(
            "MANUAL", sequence=1, match_label="contains", match_label_param="RESEQPROBE"
        )
        automated = self._model(
            "AUTOMATED",
            sequence=2,
            trigger="auto_reconcile",
            match_label="contains",
            match_label_param="RESEQPROBE",
        )
        bystander = self._model(
            "BYSTANDER", sequence=3, match_label="contains", match_label_param="NOPE"
        )
        self.assertEqual(self._proposal(st_line), manual)

        model_class = type(manual)
        original = model_class._refresh_statement_line_proposals
        calls = []

        def spy(records, *args, **kwargs):
            calls.append(records)
            return original(records, *args, **kwargs)

        with patch.object(model_class, "_refresh_statement_line_proposals", spy):
            (manual + automated + bystander).web_resequence({"id": {}}, offset=1)
            self.assertEqual(calls, [], "the relative order did not change")

            (automated + manual + bystander).web_resequence({"id": {}})
            self.assertEqual(len(calls), 1)

        self.assertFalse(st_line.is_reconciled)
        self.assertEqual(self._proposal(st_line), automated)

    def test_on_demand_run_does_not_stamp_the_cron_queue(self):
        st_line = self._create_st_line(13.0, payment_ref="NOTHING TO MATCH")
        st_line._try_auto_reconcile_statement_lines()
        self.assertFalse(st_line.cron_last_check)

    def test_cron_batches_retried_line_by_line_are_not_barren(self):
        StatementLine = type(self.env["account.bank.statement.line"])
        genuine = StatementLine._try_auto_reconcile_statement_lines

        def explode(records, *args, **kwargs):
            if len(records) > 1:
                raise ValueError("boom")
            return genuine(records, *args, **kwargs)

        st_lines = self.env["account.bank.statement.line"]
        for index in range(8):
            st_lines |= self._create_st_line(
                -5.0 - index, payment_ref=f"NOTHING {index}", update_create_date=False
            )
        with patch.object(
            StatementLine, "_try_auto_reconcile_statement_lines", explode
        ):
            st_lines._cron_try_auto_reconcile_statement_lines(batch_size=2)
        self.assertEqual(st_lines.filtered("cron_last_check"), st_lines)

    def test_import_detects_partners_once(self):
        StatementLine = type(self.env["account.bank.statement.line"])
        genuine = StatementLine._set_partner_from_transaction
        calls = []

        def spy(records, *args, **kwargs):
            calls.append(records)
            return genuine(records, *args, **kwargs)

        with patch.object(StatementLine, "_set_partner_from_transaction", spy):
            self.env["account.bank.statement.line"].with_context(
                auto_statement_processing=True
            ).create(
                [
                    {
                        "journal_id": self.bank_journal.id,
                        "payment_ref": f"IMPORT {index}",
                        "partner_name": "SOMEBODY",
                        "amount": -7.0,
                        "date": "2019-01-01",
                    }
                    for index in range(3)
                ]
            )
        self.assertEqual(len(calls), 1)

    def test_a_later_import_batch_learns_a_partner_from_an_earlier_one(self):
        bill = self._bill(321.0, "ZREF12345")
        with patch.object(reconcile_module, "AUTO_STATEMENT_PROCESSING_BATCH_SIZE", 1):
            paid, later = (
                self.env["account.bank.statement.line"]
                .with_context(auto_statement_processing=True)
                .create(
                    [
                        {
                            "journal_id": self.bank_journal.id,
                            "payment_ref": payment_ref,
                            "partner_name": "QQX ZETA CO",
                            "amount": amount,
                            "date": "2019-01-01",
                        }
                        for payment_ref, amount in (
                            ("pay ZREF12345", -bill.amount_total),
                            ("misc transfer", -5.0),
                        )
                    ]
                )
            )
        self.assertTrue(paid.is_reconciled)
        self.assertEqual(paid.partner_id, self.partner_a)
        self.assertEqual(later.partner_id, self.partner_a)

    def test_inconsistent_statements_are_read_for_the_report_journal_only(self):
        statements = self.env["account.bank.statement"].create(
            [
                {
                    "name": "ST1",
                    "balance_start": 0.0,
                    "balance_end_real": 10.0,
                    "line_ids": [Command.set(self._create_st_line(10.0).ids)],
                },
                {
                    "name": "ST2",
                    "balance_start": 99.0,
                    "balance_end_real": 109.0,
                    "line_ids": [Command.set(self._create_st_line(10.0).ids)],
                },
            ]
        )
        statement_class = type(statements)
        original = statement_class._get_invalid_statement_ids
        scopes = []

        def spy(records, *args, **kwargs):
            scopes.append(kwargs.get("all_statements"))
            return original(records, *args, **kwargs)

        with patch.object(statement_class, "_get_invalid_statement_ids", spy):
            inconsistent = self.env[
                "account.bank.reconciliation.report.handler"
            ]._get_inconsistent_statements(
                {"date": {"date_to": "2019-12-31"}}, self.bank_journal
            )
        self.assertEqual(inconsistent, statements[1])
        self.assertNotIn(True, scopes)

    def test_structured_references_validate_raw_input(self):
        self.assertTrue(sr.is_valid_structured_reference("+++020/3430/57642+++"))
        self.assertTrue(sr.is_valid_structured_reference("RF18 5390 0754 7034"))
        self.assertTrue(
            sr.is_valid_structured_reference_for_country(" 020 3430 57642 ", "BE")
        )
        self.assertFalse(sr.is_valid_structured_reference("   "))
        self.assertFalse(sr.is_valid_structured_reference(False))
        self.assertFalse(sr.is_valid_structured_reference_si("SI01 1-2-3-4"))
