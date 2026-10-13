from unittest.mock import patch

from odoo import Command, fields
from odoo.exceptions import RedirectWarning, ValidationError
from odoo.fields import Domain
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


@tagged("post_install", "-at_install")
class TestMarinBankRecFixes(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.eur = cls.setup_other_currency("EUR")
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.expense = cls.company_data["default_account_expense"]
        cls.revenue = cls.company_data["default_account_revenue"]
        cls.eur_journal = cls.env["account.journal"].create(
            {
                "name": "EUR bank",
                "type": "bank",
                "code": "BEUR",
                "currency_id": cls.eur.id,
            }
        )

    def _st_line(self, amount, payment_ref="turlututu", **kw):
        return self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.bank_journal.id,
                "payment_ref": payment_ref,
                "amount": amount,
                "date": "2019-01-01",
                **kw,
            }
        )

    def _model(self, name, **kw):
        kw.setdefault(
            "line_ids",
            [
                Command.create(
                    {
                        "account_id": self.expense.id,
                        "amount_type": "percentage",
                        "amount_string": "100",
                    }
                )
            ],
        )
        return self.env["account.reconcile.model"].create({"name": name, **kw})

    def _invoice(self, amount, currency=None, **kw):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-01",
                "currency_id": (currency or self.env.company.currency_id).id,
                "invoice_line_ids": [
                    Command.create(
                        {"name": "line", "price_unit": amount, "tax_ids": []}
                    )
                ],
                **kw,
            }
        )
        invoice.action_post()
        return invoice

    def _receivable(self, move):
        return move.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )

    def _proposal(self, st_line):
        return st_line.move_id.line_ids.filtered(
            lambda line: line.account_id == st_line.journal_id.suspense_account_id
        ).reconcile_model_id

    def test_label_regex_is_validated_by_the_engine_that_runs_it(self):
        with self.assertRaises(ValidationError):
            self._model(
                "PY ONLY",
                match_label="match_regex",
                match_label_param="(?P<x>abc)",
            )

    def test_editing_a_lower_priority_model_keeps_the_higher_priority_proposal(self):
        line = self._st_line(100.0, payment_ref="PRIOPROBE PAYMENT")
        self.env.flush_all()
        first = self._model(
            "FIRST", sequence=1, match_label="contains", match_label_param="PRIOPROBE"
        )
        second = self._model(
            "SECOND", sequence=2, match_label="contains", match_label_param="NOMATCH"
        )
        self.assertEqual(self._proposal(line), first)
        second.write({"match_label_param": "PRIOPROBE"})
        self.assertEqual(self._proposal(line), first)

    def test_a_line_freed_by_its_model_falls_to_the_next_model(self):
        line = self._st_line(100.0, payment_ref="FREEPROBE PAYMENT")
        self.env.flush_all()
        first = self._model(
            "FIRST", sequence=1, match_label="contains", match_label_param="FREEPROBE"
        )
        second = self._model(
            "SECOND", sequence=2, match_label="contains", match_label_param="FREEPROBE"
        )
        self.assertEqual(self._proposal(line), first)
        first.write({"match_label_param": "NOMATCH"})
        self.assertEqual(self._proposal(line), second)

    def test_open_balance_in_foreign_currency_uses_the_statement_line_rate(self):
        st_line = self._st_line(
            1000.0,
            partner_id=self.partner_a.id,
            foreign_currency_id=self.eur.id,
            amount_currency=800.0,
        )
        st_line.set_line_bank_statement_line(self._receivable(self._invoice(300.0)).ids)
        suspense = st_line.line_ids.filtered(
            lambda line: line.account_id == self.bank_journal.suspense_account_id
        )
        self.assertRecordValues(
            suspense,
            [
                {
                    "currency_id": self.eur.id,
                    "balance": -700.0,
                    "amount_currency": -560.0,
                }
            ],
        )

    def test_amount_matching_does_not_compare_company_and_journal_amounts(self):
        invoice = self._invoice(100.0, currency=self.eur)
        st_line = self._st_line(
            200.0, journal_id=self.eur_journal.id, partner_id=self.partner_a.id
        )
        st_line._try_auto_reconcile_statement_lines()
        self.assertEqual(self._receivable(invoice).amount_residual_currency, 100.0)
        self.assertFalse(st_line.is_reconciled)

    def test_fixed_and_regex_model_lines_convert_the_balance(self):
        st_line = self._st_line(
            200.0, journal_id=self.eur_journal.id, payment_ref="WIRE FEE 10.00"
        )
        model = self._model(
            "FEES",
            line_ids=[
                Command.create(
                    {
                        "account_id": self.expense.id,
                        "amount_type": "fixed",
                        "amount_string": "4",
                    }
                ),
                Command.create(
                    {
                        "account_id": self.expense.id,
                        "amount_type": "regex",
                        "amount_string": r"FEE ([\d.]+)",
                    }
                ),
            ],
        )
        vals_list = model._apply_lines_for_bank_widget(
            residual_amount_currency=-200.0,
            residual_balance=-100.0,
            partner=self.partner_a,
            st_line=st_line,
        )
        self.assertEqual(
            [(vals["amount_currency"], vals["balance"]) for vals in vals_list],
            [(-4.0, -2.0), (-10.0, -5.0)],
        )

    def test_an_automatic_trigger_assigns_the_activity_to_the_acting_user(self):
        line = self._st_line(100.0, payment_ref="ACTPROBE PAYMENT")
        self.env.flush_all()
        self._model(
            "ACT",
            trigger="auto_reconcile",
            match_label="contains",
            match_label_param="ACTPROBE",
            next_activity_type_id=self.env.ref("mail.mail_activity_data_todo").id,
        )
        self.assertEqual(line.move_id.activity_ids.user_id, self.env.user)

    def test_a_scoped_cron_run_leaves_other_lines_alone(self):
        mine = self._st_line(111.0)
        other = self._st_line(222.0)
        mine._cron_try_auto_reconcile_statement_lines(batch_size=100)
        self.assertTrue(mine.cron_last_check)
        self.assertFalse(other.cron_last_check)

    def test_payment_reference_matching_ignores_case(self):
        invoice = self._invoice(100.0, payment_reference="Pedido 45678")
        st_line = self._st_line(
            60.0, payment_ref="PAGO PEDIDO 45678", partner_id=self.partner_a.id
        )
        st_line._try_auto_reconcile_statement_lines()
        self.assertEqual(self._receivable(invoice).amount_residual, 40.0)

    def test_outstanding_matching_needs_a_whole_reference(self):
        payments = self.env["account.payment"].create(
            [
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.partner_a.id,
                    "amount": 100.0,
                    "date": "2019-01-01",
                    "journal_id": self.bank_journal.id,
                    "memo": memo,
                }
                for memo in ("PAY20260001", "PAY202600015")
            ]
        )
        payments.action_post()
        st_line = self._st_line(100.0, payment_ref="Transfer PAY202600015")
        st_line._try_auto_reconcile_statement_lines()
        self.assertEqual(
            [
                payment.move_id.line_ids.filtered(
                    lambda line, p=payment: line.account_id == p.liquidity_account_id
                ).reconciled
                for payment in payments
            ],
            [False, True],
        )

    def test_debit_and_credit_write_through_to_the_amount(self):
        st_line = self._st_line(100.0)
        st_line.write({"debit": 30.0})
        self.assertEqual(st_line.amount, -30.0)
        st_line.write({"credit": 45.0})
        self.assertEqual(st_line.amount, 45.0)

    def test_editing_a_tax_line_account_keeps_its_analytic_lines(self):
        plan = self.env["account.analytic.plan"].create({"name": "Plan"})
        analytic = self.env["account.analytic.account"].create(
            {"name": "Analytic", "plan_id": plan.id}
        )
        tax = self.env["account.tax"].create(
            {"name": "analytic tax", "amount": 10, "analytic": True}
        )
        st_line = self._st_line(110.0)
        st_line.set_account_bank_statement_line(
            st_line.line_ids[-1].id, self.revenue.id
        )
        st_line.edit_reconcile_line(
            st_line.line_ids[-1].id,
            {
                "tax_ids": [Command.link(tax.id)],
                "analytic_distribution": {str(analytic.id): 100},
            },
        )
        tax_line = st_line.line_ids.filtered("tax_line_id")
        analytic_lines = tax_line.analytic_line_ids
        self.assertTrue(analytic_lines)
        st_line.edit_reconcile_line(tax_line.id, {"account_id": self.expense.id})
        self.assertTrue(analytic_lines.exists())

    def test_reconciliation_report_ignores_draft_statement_lines(self):
        posted = self._st_line(100.0)
        drafted = self._st_line(50.0)
        self.env["account.bank.statement"].create(
            {
                "name": "ST",
                "balance_start": 0.0,
                "line_ids": [Command.set((posted + drafted).ids)],
            }
        )
        drafted.move_id.action_draft()
        _statement, balance_end, difference, not_matching = self.env[
            "account.bank.reconciliation.report.handler"
        ]._get_balances(
            {"date": {"date_to": "2019-12-31"}},
            self.bank_journal,
            100.0,
            self.env.company.currency_id,
        )
        self.assertEqual((balance_end, difference, not_matching), (100.0, 0.0, False))

    def test_statement_validity_is_computed_in_one_query(self):
        statements = self.env["account.bank.statement"].create(
            [
                {
                    "name": f"ST{index}",
                    "line_ids": [Command.set(self._st_line(10.0 + index).ids)],
                }
                for index in range(3)
            ]
        )
        statement_class = type(statements)
        original = statement_class._get_invalid_statement_ids
        calls = []

        def spy(records, *args, **kwargs):
            calls.append(records)
            return original(records, *args, **kwargs)

        statements.invalidate_recordset(["is_valid"])
        with patch.object(statement_class, "_get_invalid_statement_ids", spy):
            statements.mapped("is_valid")
        self.assertEqual(len(calls), 1)

    def _run_wizard(self):
        return (
            self.env["wizard.account.bank.statement.line.reconcile.auto"]
            .create(
                {
                    "journal_id": self.bank_journal.id,
                    "from_date": "2018-12-01",
                    "to_date": "2019-01-31",
                }
            )
            .action_auto_reconcile()
        )

    def test_auto_reconcile_wizard_runs_the_batch_once(self):
        lines = self._st_line(11.0) + self._st_line(12.0) + self._st_line(13.0)
        line_class = type(lines)
        original = line_class._try_auto_reconcile_statement_lines
        calls = []

        def spy(records, *args, **kwargs):
            calls.append(records)
            return original(records, *args, **kwargs)

        with patch.object(line_class, "_try_auto_reconcile_statement_lines", spy):
            action = self._run_wizard()
        self.assertEqual(len(calls), 1)
        self.assertEqual(action["params"]["type"], "success")

    def test_auto_reconcile_wizard_reports_the_lines_it_gave_up_on(self):
        failing = self._st_line(21.0)
        self._st_line(22.0)
        line_class = type(failing)
        original = line_class._try_auto_reconcile_statement_lines

        def flaky(records, *args, **kwargs):
            if failing in records:
                raise ValueError("boom")
            return original(records, *args, **kwargs)

        with patch.object(line_class, "_try_auto_reconcile_statement_lines", flaky):
            action = self._run_wizard()
        self.assertEqual(action["params"]["type"], "warning")
        self.assertEqual(
            action["params"]["message"],
            "Automatic reconciliation finished on 2 transactions; "
            "1 of them could not be processed.",
        )

    def test_statement_form_lines_accept_debit_and_credit(self):
        statement_form = Form(
            self.env["account.bank.statement"].with_context(
                default_journal_id=self.bank_journal.id
            ),
            view="account.view_bank_statement_form_bank_rec_widget",
        )
        statement_form.name = "debit credit probe"
        with statement_form.line_ids.new() as line_form:
            line_form.payment_ref = "credit line"
            line_form.date = fields.Date.from_string("2019-01-01")
            line_form.credit = 100.0
        with statement_form.line_ids.new() as line_form:
            line_form.payment_ref = "debit line"
            line_form.date = fields.Date.from_string("2019-01-01")
            line_form.debit = 40.0
        statement = statement_form.save()
        self.assertEqual(
            statement.line_ids.sorted("payment_ref").mapped("amount"), [100.0, -40.0]
        )

    def test_debit_and_credit_values_create_and_load_statement_lines(self):
        Line = self.env["account.bank.statement.line"]
        created = Line.create(
            [
                {
                    "journal_id": self.bank_journal.id,
                    "date": "2019-01-01",
                    "payment_ref": "both",
                    "debit": 0.0,
                    "credit": 100.0,
                    "amount": 100.0,
                },
                {
                    "journal_id": self.bank_journal.id,
                    "date": "2019-01-01",
                    "payment_ref": "debit only",
                    "debit": 40.0,
                },
            ]
        )
        self.assertEqual(created.mapped("amount"), [100.0, -40.0])
        result = Line.load(
            ["journal_id/.id", "date", "payment_ref", "debit", "credit"],
            [[str(self.bank_journal.id), "2019-01-01", "loaded", "25", "0"]],
        )
        self.assertFalse(result["messages"])
        self.assertEqual(Line.browse(result["ids"]).amount, -25.0)

    def test_a_regex_only_postgresql_understands_is_rejected_quietly(self):
        with (
            self.assertNoLogs("odoo.db.cursor", "ERROR"),
            self.assertRaises(ValidationError),
        ):
            self._model(
                "PG ONLY",
                match_label="match_regex",
                match_label_param=r"\mTELMEX\M",
            )
        with self.assertRaises(ValidationError):
            self._model(
                "PY ONLY QUIET", match_label="match_regex", match_label_param="(?P<x>a)"
            )
        self.assertTrue(
            self._model(
                "BOTH", match_label="match_regex", match_label_param=r"TELMEX\s+\d+"
            )
        )

    def test_references_are_bounded_by_any_non_alphanumeric_character(self):
        payments = self.env["account.payment"].create(
            [
                {
                    "payment_type": "inbound",
                    "partner_type": "customer",
                    "partner_id": self.partner_a.id,
                    "amount": amount,
                    "date": "2019-01-01",
                    "journal_id": self.bank_journal.id,
                    "memo": memo,
                }
                for memo, amount in (("PAYX2026001", 70.0), ("PAYX2026002", 80.0))
            ]
        )
        payments.action_post()
        lines = self._st_line(70.0, payment_ref="Transfer REF:PAYX2026001") + (
            self._st_line(80.0, payment_ref="PAGO (PAYX2026002)")
        )
        lines._try_auto_reconcile_statement_lines()
        self.assertEqual(lines.mapped("is_reconciled"), [True, True])

    def test_a_zero_amount_foreign_line_converts_its_suspense_at_the_dated_rate(self):
        st_line = self._st_line(
            0.0,
            partner_id=self.partner_a.id,
            foreign_currency_id=self.eur.id,
            amount_currency=0.0,
        )
        st_line.set_line_bank_statement_line(self._receivable(self._invoice(300.0)).ids)
        suspense = st_line.line_ids.filtered(
            lambda line: line.account_id == self.bank_journal.suspense_account_id
        )
        expected = self.env.company.currency_id._convert(
            suspense.balance, self.eur, self.env.company, st_line.date
        )
        self.assertTrue(expected)
        self.assertEqual(suspense.currency_id, self.eur)
        self.assertAlmostEqual(suspense.amount_currency, expected)

    def test_editing_a_model_never_auto_reconciles_the_lines_it_frees(self):
        line = self._st_line(100.0, payment_ref="SIDEPROBE PAYMENT")
        self.env.flush_all()
        manual = self._model(
            "MANUAL", sequence=1, match_label="contains", match_label_param="SIDEPROBE"
        )
        automated = self._model(
            "AUTOMATED",
            sequence=2,
            trigger="auto_reconcile",
            match_label="contains",
            match_label_param="SIDEPROBE",
        )
        self.assertEqual(self._proposal(line), manual)
        manual.write({"match_label_param": "NOMATCH"})
        self.assertFalse(line.is_reconciled)
        self.assertEqual(self._proposal(line), automated)


@tagged("post_install", "-at_install")
class TestMarinBankRecAuditFixes(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.Line = cls.env["account.bank.statement.line"]

    def _invoice(self, amount, currency=None, **kw):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-01-01",
                "currency_id": (currency or self.env.company.currency_id).id,
                "invoice_line_ids": [
                    Command.create(
                        {"name": "line", "price_unit": amount, "tax_ids": []}
                    )
                ],
                **kw,
            }
        )
        invoice.action_post()
        return invoice

    def _receivable(self, move):
        return move.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )

    def _held_elsewhere(self, held):
        return patch.object(
            type(self.Line),
            "_get_domain_settled_elsewhere",
            lambda _self: Domain("id", "in", held.ids),
        )

    def test_a_failed_cron_batch_leaves_no_partial_entry(self):
        tax = self.env["account.tax"].create({"name": "lock probe", "amount": 10})
        model = self._create_reconcile_model(
            trigger="auto_reconcile",
            match_label="contains",
            match_label_param="NOMATCH",
            line_ids=[{"tax_ids": [Command.set(tax.ids)]}],
        )
        locked = self._create_st_line(100.0, payment_ref="LOCKPROBE 1")
        free = self._create_st_line(50.0, payment_ref="FREE 1")
        before = locked.move_id.line_ids
        self.env.company.account_config_id.tax_lock_date = "2019-01-31"
        model.with_context(defer_proposal_refresh=True).write(
            {"match_label_param": "LOCKPROBE"}
        )

        (locked | free)._cron_try_auto_reconcile_statement_lines(batch_size=10)

        locked.invalidate_recordset()
        self.assertEqual(locked.move_id.line_ids, before)
        self.assertFalse(locked.is_reconciled)
        self.assertTrue(locked.cron_last_check)

    def test_a_failed_batch_selection_does_not_stop_the_cron(self):
        st_line = self._create_st_line(50.0, payment_ref="SELECTPROBE 1")
        StatementLine = type(self.env["account.bank.statement.line"])
        original = StatementLine._get_domain_auto_reconcile_due
        failures = []

        def fail_once(records, run_start):
            if not failures:
                failures.append(run_start)
                records.env.cr.execute("SELECT 1 / 0")
            return original(records, run_start)

        with patch.object(StatementLine, "_get_domain_auto_reconcile_due", fail_once):
            st_line._cron_try_auto_reconcile_statement_lines(batch_size=10)

        self.assertTrue(failures)
        self.assertTrue(st_line.cron_last_check)

    def test_auto_reconcile_leaves_a_reconciled_line_alone(self):
        st_line = self._create_st_line(
            100.0, payment_ref="PAY C2PROBE77", partner_id=self.partner_a.id
        )
        st_line.set_line_bank_statement_line(self._receivable(self._invoice(100.0)).ids)
        self.assertTrue(st_line.is_reconciled)
        other = self._invoice(50.0, payment_reference="C2PROBE77")

        st_line._try_auto_reconcile_statement_lines()

        self.assertEqual(self._receivable(other).amount_residual, 50.0)
        self.assertTrue(st_line.is_reconciled)

    def test_draft_proposals_skip_a_line_settled_elsewhere(self):
        self.env["account.move"].create(
            [
                {
                    "move_type": "in_invoice",
                    "partner_id": self.partner_a.id,
                    "invoice_date": "2019-01-05",
                    "invoice_line_ids": [
                        Command.create(
                            {"name": "draft", "price_unit": amount, "tax_ids": []}
                        )
                    ],
                }
                for amount in (1234.5, 2345.6)
            ]
        )
        held = self._create_st_line(-1234.5, payment_ref="HELD")
        free = self._create_st_line(-2345.6, payment_ref="FREE")

        with self._held_elsewhere(held):
            (held | free)._try_auto_reconcile_statement_lines()

        self.assertFalse(held.draft_match_proposal_ids)
        self.assertTrue(free.draft_match_proposal_ids)

    def test_a_new_model_skips_a_line_settled_elsewhere(self):
        held = self._create_st_line(100.0, payment_ref="C3PROBE held")
        free = self._create_st_line(100.0, payment_ref="C3PROBE free")

        with self._held_elsewhere(held):
            self._create_reconcile_model(
                trigger="auto_reconcile",
                match_label="contains",
                match_label_param="C3PROBE",
                line_ids=[{}],
            )

        self.assertEqual((held | free).mapped("is_reconciled"), [False, True])

    def test_an_edited_model_clears_its_proposal_on_a_line_settled_elsewhere(self):
        held = self._create_st_line(100.0, payment_ref="C3TAG held")
        free = self._create_st_line(100.0, payment_ref="C3TAG free")
        model = self._create_reconcile_model(
            trigger="manual",
            match_label="contains",
            match_label_param="C3TAG",
            line_ids=[{}],
        )
        self.assertEqual(
            (held | free).move_id.line_ids.reconcile_model_id, model, "proposed"
        )

        with self._held_elsewhere(held):
            model.match_label_param = "NOMATCH"

        self.assertFalse(held.move_id.line_ids.reconcile_model_id)
        self.assertFalse(free.move_id.line_ids.reconcile_model_id)

    def test_a_partner_taken_from_the_match_is_not_manual(self):
        st_line = self._create_st_line(100.0)
        st_line.set_line_bank_statement_line(self._receivable(self._invoice(100.0)).ids)
        self.assertEqual(st_line.partner_id, self.partner_a)
        self.assertFalse(st_line.is_partner_manual)

    def _foreign_suspense_after(self, *invoices):
        st_line = self._create_st_line(
            100.0,
            partner_id=self.partner_a.id,
            foreign_currency_id=self.other_currency.id,
            amount_currency=200.0,
        )
        for invoice in invoices:
            st_line.set_line_bank_statement_line(self._receivable(invoice).ids)
        return st_line.line_ids.filtered(
            lambda line: line.account_id == self.bank_journal.suspense_account_id
        )

    def test_a_second_foreign_match_keeps_the_exact_open_amount(self):
        suspense = self._foreign_suspense_after(
            self._invoice(0.03, currency=self.other_currency),
            self._invoice(0.03, currency=self.other_currency),
        )
        self.assertEqual(suspense.amount_currency, -199.94)

    def test_a_foreign_match_after_a_company_currency_one_converts_it(self):
        suspense = self._foreign_suspense_after(
            self._invoice(30.0),
            self._invoice(0.04, currency=self.other_currency),
        )
        self.assertEqual(suspense.amount_currency, -139.96)

    def test_counterparty_key_follows_the_journal(self):
        other_journal = self.company_data["default_journal_bank"].copy()
        st_line = self._create_st_line(100.0, payment_ref="KEYPROBE")
        st_line.move_id.action_draft()
        with patch.object(
            type(self.Line),
            "_get_counterparty_key",
            lambda line: line.journal_id.code,
        ):
            st_line.write({"name": "/", "journal_id": other_journal.id})
            self.assertEqual(st_line.counterparty_key, other_journal.code)

    def test_a_date_group_mixing_journals_shows_no_running_balance(self):
        other_journal = self.bank_journal.copy()
        self._create_st_line(10.0, date="2019-01-01")
        self._create_st_line(1000.0, date="2019-01-01", journal_id=other_journal.id)
        groups = self.Line.with_context(
            show_running_balance_latest=True
        ).formatted_read_group(
            [
                ("journal_id", "in", (self.bank_journal | other_journal).ids),
                ("date", "=", "2019-01-01"),
            ],
            ["date:day"],
            ["amount:sum"],
        )
        self.assertEqual([group["running_balance"] for group in groups], [False])
        groups = self.Line.with_context(
            show_running_balance_latest=True
        ).formatted_read_group(
            [("journal_id", "=", other_journal.id), ("date", "=", "2019-01-01")],
            ["date:day"],
            ["amount:sum"],
        )
        self.assertEqual([group["running_balance"] for group in groups], [1000.0])

    def _charges_setup(self):
        bank = self.env["res.partner"].create({"name": "The Charging Bank"})
        self.bank_journal.write(
            {"bank_charges_partner_id": bank.id, "bank_charges_pattern": r"^COM "}
        )
        lines = self._create_st_line(
            -830.0, date="2019-03-04", payment_ref="COM SERV NET"
        ) | self._create_st_line(-450.0, date="2019-03-05", payment_ref="COM ADMON")

        def bill(total):
            move = self.env["account.move"].create(
                {
                    "move_type": "in_invoice",
                    "partner_id": bank.id,
                    "invoice_date": "2019-04-01",
                    "invoice_line_ids": [
                        Command.create(
                            {
                                "name": "charges",
                                "price_unit": total,
                                "tax_ids": [],
                                "account_id": self.company_data[
                                    "default_account_expense"
                                ].id,
                            }
                        )
                    ],
                }
            )
            move.action_post()
            return move

        return lines, bill

    def test_period_charges_ignore_a_draft_transaction(self):
        lines, bill = self._charges_setup()
        drafted = self._create_st_line(
            -100.0, date="2019-03-06", payment_ref="COM DRAFTED"
        )
        drafted.move_id.action_draft()
        charges_bill = bill(1280.0)

        lines._try_auto_reconcile_statement_lines()

        self.assertEqual(lines.mapped("is_reconciled"), [True, True])
        self.assertEqual(charges_bill.payment_state, "paid")
        self.assertEqual(drafted.move_id.state, "draft")

    def test_period_charges_count_only_what_is_still_open(self):
        lines, bill = self._charges_setup()
        other = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2019-03-01",
                "invoice_line_ids": [
                    Command.create({"name": "x", "price_unit": 30.0, "tax_ids": []})
                ],
            }
        )
        other.action_post()
        lines[0].set_line_bank_statement_line(
            other.line_ids.filtered(
                lambda line: line.account_id.account_type == "liability_payable"
            ).ids
        )
        self.assertFalse(lines[0].is_reconciled)
        charges_bill = bill(1250.0)

        lines._try_auto_reconcile_statement_lines()

        self.assertEqual(lines.mapped("is_reconciled"), [True, True])
        self.assertEqual(charges_bill.payment_state, "paid")


@tagged("post_install", "-at_install")
class TestMarinUnreconciledLockRedirect(AccountTestInvoicingCommon):
    def test_locking_over_an_unreconciled_transaction_opens_bank_matching(self):
        st_line = self.env["account.bank.statement.line"].create(
            {
                "journal_id": self.company_data["default_journal_bank"].id,
                "date": "2019-01-15",
                "payment_ref": "unmatched",
                "amount": 100.0,
            }
        )
        with self.assertRaises(RedirectWarning) as caught:
            self.env.company.account_config_id.fiscalyear_lock_date = "2019-01-31"
        action = caught.exception.args[1]
        widget_action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account.action_bank_statement_line_transactions_kanban"
        )
        self.assertEqual(action["id"], widget_action["id"])
        self.assertIn(("id", "in", st_line.ids), action["domain"])
