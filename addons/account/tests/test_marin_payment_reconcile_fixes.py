from unittest.mock import patch

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


@tagged("post_install", "-at_install")
class TestMarinPaymentReconcileFixes(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.bank_journal.inbound_payment_channel_ids.payment_account_id = False

    def setUp(self):
        super().setUp()
        self.full_accounting = True
        self.startPatcher(
            patch.object(
                type(self.env["account.move"]),
                "_has_full_accounting",
                lambda _self: self.full_accounting,
            )
        )

    def _moveless_payment(self, invoice_lines, date="2019-01-01"):
        payment = self.env["account.payment"].create(
            {
                "amount": sum(invoice_lines.mapped("amount_residual")),
                "date": date,
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                "invoice_ids": [Command.set(invoice_lines.move_id.ids)],
            }
        )
        payment.action_post()
        self.assertEqual(payment.state, "in_process")
        self.assertFalse(payment.move_id)
        return payment

    def _invoice_line(self, amount, **kwargs):
        return self._create_invoice_line(
            "out_invoice",
            invoice_date="2019-01-01",
            invoice_line_ids=[{"price_unit": amount}],
            **kwargs,
        )

    def test_a_moveless_payment_is_valid_inside_a_forced_entry_context(self):
        payment = self._moveless_payment(self._invoice_line(100.0))

        payment.with_context(force_payment_move=True)._check_move_id()

        self.full_accounting = False
        with self.assertRaises(ValidationError):
            payment._check_move_id()

    def test_a_forced_entry_belongs_to_the_payment_created_for_it(self):
        waiting = self._moveless_payment(self._invoice_line(100.0))
        invoice_line = self._invoice_line(200.0)
        st_line = self._create_st_line(200.0, date="2019-01-05")
        self.env.add_to_compute(waiting._fields["outstanding_account_id"], waiting)

        forced = st_line._create_payment_with_move_from_invoice(invoice_line.move_id)

        self.assertTrue(forced.is_entry_required)
        self.assertTrue(forced.outstanding_account_id)
        self.assertTrue(forced.move_id)
        self.assertRecordValues(
            waiting, [{"is_entry_required": False, "outstanding_account_id": False}]
        )
        forced.payment_channel_id = forced.payment_channel_id
        self.assertTrue(forced.outstanding_account_id)

    def test_statement_counterparts_follow_the_payments_chronologically(self):
        created_first = self._moveless_payment(self._invoice_line(100.0), "2019-01-02")
        dated_first = self._moveless_payment(self._invoice_line(200.0), "2019-01-01")
        created_last = self._moveless_payment(self._invoice_line(300.0), "2019-01-02")
        st_line = self._create_st_line(600.0, date="2019-01-05")

        amls, _has_exchange_diff = (
            created_last + created_first + dated_first
        )._get_amls_for_reconciliation(st_line)

        self.assertEqual(
            [vals["amount_currency"] for vals in amls], [-200.0, -100.0, -300.0]
        )

    def test_counterpart_vals_name_only_move_line_fields(self):
        invoice_line = self._invoice_line(100.0)
        payment = self._moveless_payment(invoice_line)
        payment.amount = 150.0
        st_line = self._create_st_line(150.0, date="2019-01-05")
        line_fields = set(self.env["account.move.line"]._fields)

        without_move = payment._get_amls_for_payment_without_move()
        for_statement, _has_exchange_diff = payment._get_amls_for_reconciliation(
            st_line
        )

        self.assertEqual(len(without_move), 2)
        self.assertEqual(len(for_statement), 2)
        for vals in without_move + for_statement:
            self.assertLessEqual(set(vals), line_fields)

    def test_a_moveless_payment_paid_through_the_statement_is_bank_matched(self):
        invoice_line = self._invoice_line(100.0)
        payment = self._moveless_payment(invoice_line)
        st_line = self._create_st_line(100.0, date="2019-01-05")
        amls, _has_exchange_diff = payment._get_amls_for_reconciliation(st_line)

        st_line._reconcile_with_payments(payment, amls)

        self.assertEqual(invoice_line.move_id.payment_state, "paid")
        self.assertRecordValues(payment, [{"state": "paid", "is_bank_matched": True}])

    def test_both_moveless_allocations_value_a_foreign_line_alike(self):
        currency = self.setup_other_currency(
            "CHF", rates=[("2017-01-01", 2.0), ("2019-01-01", 1.5), ("2019-01-05", 1.6)]
        )
        invoice_line = self._create_invoice_line(
            "out_invoice",
            invoice_date="2017-01-01",
            currency_id=currency.id,
            invoice_line_ids=[{"price_unit": 100.0}],
        )
        self.assertEqual(invoice_line.amount_residual, 50.0)
        payment = self.env["account.payment"].create(
            {
                "amount": 70.0,
                "date": "2019-01-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                "invoice_ids": [Command.set(invoice_line.move_id.ids)],
            }
        )
        payment.action_post()
        st_line = self._create_st_line(70.0, date="2019-01-05")

        def figures(vals_list):
            return [
                (
                    bool(vals.get("reconciled_lines_ids")),
                    vals["currency_id"],
                    vals["amount_currency"],
                    vals["balance"],
                )
                for vals in vals_list
            ]

        without_move = payment._get_amls_for_payment_without_move(date=st_line.date)
        for_statement, _has_exchange_diff = payment._get_amls_for_reconciliation(
            st_line
        )

        company_currency = self.company_data["currency"].id
        expected = [
            (True, company_currency, -62.5, -62.5),
            (False, company_currency, -7.5, -7.5),
        ]
        self.assertEqual(figures(without_move), expected)
        self.assertEqual(figures(for_statement), expected)

        st_line._reconcile_with_payments(payment, for_statement)
        self.assertRecordValues(
            invoice_line,
            [
                {
                    "reconciled": True,
                    "amount_residual": 0.0,
                    "amount_residual_currency": 0.0,
                }
            ],
        )

    def _foreign_moveless_payment(self, currency, amount, payment_currency=None):
        invoice_line = self._create_invoice_line(
            "out_invoice",
            invoice_date="2017-01-01",
            currency_id=currency.id,
            invoice_line_ids=[{"price_unit": 100.0}],
        )
        payment = self.env["account.payment"].create(
            {
                "amount": amount,
                "currency_id": (payment_currency or self.company_data["currency"]).id,
                "date": "2019-01-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                "invoice_ids": [Command.set(invoice_line.move_id.ids)],
            }
        )
        payment.action_post()
        self.assertFalse(payment.move_id)
        return invoice_line, payment

    def _reconcile_moveless(self, path, payment, st_line):
        if path == "statement":
            amls, has_exchange_diff = payment._get_amls_for_reconciliation(st_line)
            self.assertTrue(has_exchange_diff)
        else:
            amls = payment._get_amls_for_payment_without_move(date=st_line.date)
        st_line._reconcile_with_payments(payment, amls)

    def _assert_settled_with_exchange_difference(self, invoice_line, st_line, gain):
        counterpart = st_line.move_id.line_ids.filtered(
            lambda line: invoice_line in line.reconciled_lines_ids
        )
        self.assertRecordValues(
            invoice_line + counterpart,
            [
                {"reconciled": True, "amount_residual": 0.0},
                {"reconciled": True, "amount_residual": 0.0},
            ],
        )
        exchange_move = (
            counterpart.matched_debit_ids | counterpart.matched_credit_ids
        ).exchange_move_id
        self.assertEqual(len(exchange_move), 1)
        self.assertAlmostEqual(
            sum(
                exchange_move.line_ids.filtered(
                    lambda line: line.account_id == invoice_line.account_id
                ).mapped("balance")
            ),
            gain,
        )

    def test_a_moveless_payment_in_the_invoice_currency_books_the_exchange(self):
        currency = self.setup_other_currency(
            "CHF", rates=[("2017-01-01", 2.0), ("2019-01-01", 1.5)]
        )
        for path in ("statement", "without_move"):
            with self.subTest(path=path):
                invoice_line, payment = self._foreign_moveless_payment(
                    currency, 100.0, payment_currency=currency
                )
                st_line = self._create_st_line(66.67, date="2019-01-05")

                self._reconcile_moveless(path, payment, st_line)

                self._assert_settled_with_exchange_difference(
                    invoice_line, st_line, 16.67
                )

    def test_a_moveless_company_currency_payment_books_the_exchange(self):
        currency = self.setup_other_currency(
            "CHF", rates=[("2017-01-01", 2.0), ("2019-01-05", 1.6)]
        )
        for path in ("statement", "without_move"):
            with self.subTest(path=path):
                invoice_line, payment = self._foreign_moveless_payment(currency, 70.0)
                st_line = self._create_st_line(70.0, date="2019-01-05")

                self._reconcile_moveless(path, payment, st_line)

                self._assert_settled_with_exchange_difference(
                    invoice_line, st_line, 12.5
                )
                leftover = st_line.move_id.line_ids.filtered_domain(
                    [
                        ("account_id", "=", invoice_line.account_id.id),
                        ("reconciled", "=", False),
                    ]
                )
                self.assertRecordValues(leftover, [{"amount_residual": -7.5}])

    def test_a_multi_invoice_moveless_payment_loses_paid_with_one_bank_match(self):
        invoice_lines = self._invoice_line(60.0) + self._invoice_line(40.0)
        payment = self._moveless_payment(invoice_lines)
        st_line = self._create_st_line(100.0, date="2019-01-05")
        amls, _has_exchange_diff = payment._get_amls_for_reconciliation(st_line)
        st_line._reconcile_with_payments(payment, amls)
        self.assertEqual(payment.state, "paid")

        (
            invoice_lines[0].matched_debit_ids | invoice_lines[0].matched_credit_ids
        ).unlink()

        self.assertRecordValues(
            payment, [{"state": "in_process", "is_bank_matched": False}]
        )

    def test_a_moveless_payment_stays_paid_when_another_bank_line_is_unmatched(self):
        invoice_line = self._invoice_line(100.0)
        payment = self.env["account.payment"].create(
            {
                "amount": 60.0,
                "date": "2019-01-01",
                "partner_id": self.partner_a.id,
                "partner_type": "customer",
                "payment_type": "inbound",
                "journal_id": self.bank_journal.id,
                "invoice_ids": [Command.set(invoice_line.move_id.ids)],
            }
        )
        payment.action_post()
        payment_st_line = self._create_st_line(60.0, date="2019-01-05")
        amls, _has_exchange_diff = payment._get_amls_for_reconciliation(payment_st_line)
        payment_st_line._reconcile_with_payments(payment, amls)
        other_st_line = self._create_st_line(
            40.0, date="2019-01-06", partner_id=self.partner_a.id
        )
        other_st_line.set_line_bank_statement_line(invoice_line.ids)
        self.assertTrue(invoice_line.reconciled)

        (invoice_line.matched_debit_ids | invoice_line.matched_credit_ids).filtered(
            lambda partial: (
                other_st_line.move_id
                in (partial.debit_move_id | partial.credit_move_id).move_id
            )
        ).unlink()

        self.assertEqual(invoice_line.amount_residual, 40.0)
        self.assertRecordValues(payment, [{"state": "paid", "is_bank_matched": True}])

    def test_a_credit_note_settling_the_invoices_does_not_bank_match(self):
        invoice_lines = self._invoice_line(60.0) + self._invoice_line(40.0)
        payment = self._moveless_payment(invoice_lines)
        refund_line = self._create_invoice_line(
            "out_refund",
            invoice_date="2019-01-01",
            invoice_line_ids=[{"price_unit": 100.0}],
        )

        (invoice_lines + refund_line).reconcile()

        self.assertTrue(all(invoice_lines.mapped("reconciled")))
        self.assertRecordValues(
            payment, [{"state": "in_process", "is_bank_matched": False}]
        )

    def test_register_journal_searches_do_not_grow_with_the_batches(self):
        partners = self.partner_a + self.partner_b + self.partner_a.copy()
        bills = self.env["account.move"].union(
            *(
                self._create_invoice_line(
                    "in_invoice",
                    partner_id=partner.id,
                    invoice_line_ids=[{"price_unit": 10.0}],
                ).move_id
                for partner in partners
            )
        )
        journal_model = type(self.env["account.journal"])
        register_model = type(self.env["wizard.account.move.line.pay"])
        search = journal_model._search
        available_journals = register_model._get_batch_available_journals

        def journal_searches(moves):
            self.env.invalidate_all()
            inside = []
            calls = []

            def counting_search(journal, *args, **kwargs):
                if inside:
                    calls.append(1)
                return search(journal, *args, **kwargs)

            def tracked_available_journals(register, *args, **kwargs):
                inside.append(1)
                try:
                    return available_journals(register, *args, **kwargs)
                finally:
                    inside.pop()

            with (
                patch.object(journal_model, "_search", counting_search),
                patch.object(
                    register_model,
                    "_get_batch_available_journals",
                    tracked_available_journals,
                ),
            ):
                wizard = (
                    self.env["wizard.account.move.line.pay"]
                    .with_context(active_model="account.move", active_ids=moves.ids)
                    .create({})
                )
            self.assertEqual(len(wizard.batches), len(moves))
            return len(calls)

        single = journal_searches(bills[:1])
        self.assertEqual(journal_searches(bills), single)
