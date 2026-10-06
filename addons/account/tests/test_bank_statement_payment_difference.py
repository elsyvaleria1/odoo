from odoo.tests import tagged

from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


@tagged("post_install", "-at_install")
class TestBankStatementPaymentDifference(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gain_account = cls.company_data["default_account_revenue"].copy(
            {"name": "Payment difference gain"}
        )
        cls.loss_account = cls.company_data["default_account_expense"].copy(
            {"name": "Payment difference loss"}
        )
        cls.config = cls.env.company.account_config_id
        cls.config.write(
            {
                "amount_payment_difference": 1.0,
                "payment_difference_gain_account_id": cls.gain_account.id,
                "payment_difference_loss_account_id": cls.loss_account.id,
            }
        )

    def _document(self, amount, move_type="out_invoice", **kwargs):
        account = (
            self.company_data["default_account_revenue"]
            if move_type == "out_invoice"
            else self.company_data["default_account_expense"]
        )
        return self._create_invoice_line(
            move_type,
            invoice_line_ids=[{"price_unit": amount, "account_id": account.id}],
            **kwargs,
        )

    def _difference_line(self, st_line):
        return st_line.line_ids.filtered(
            lambda line: line.account_id in self.gain_account | self.loss_account
        )

    def test_differences_within_the_limit_are_written_off(self):
        cases = [
            ("out_invoice", 1000.0, 1000.40, self.gain_account, -0.40),
            ("out_invoice", 1000.0, 999.60, self.loss_account, 0.40),
            ("in_invoice", 2226.40, -2226.00, self.gain_account, -0.40),
            ("in_invoice", 2226.00, -2226.40, self.loss_account, 0.40),
            ("out_invoice", 500.0, 501.00, self.gain_account, -1.00),
        ]
        for move_type, total, paid, account, balance in cases:
            with self.subTest(move_type=move_type, total=total, paid=paid):
                document = self._document(total, move_type=move_type)
                st_line = self._create_st_line(paid, partner_id=self.partner_a.id)

                st_line.set_line_bank_statement_line(document.ids)

                self.assertTrue(st_line.is_reconciled)
                self.assertTrue(document.reconciled, "the document is settled in full")
                difference = self._difference_line(st_line)
                self.assertRecordValues(
                    difference, [{"account_id": account.id, "balance": balance}]
                )

    def test_exact_payment_books_no_difference(self):
        document = self._document(1000.0)
        st_line = self._create_st_line(1000.0, partner_id=self.partner_a.id)

        st_line.set_line_bank_statement_line(document.ids)

        self.assertTrue(st_line.is_reconciled)
        self.assertFalse(self._difference_line(st_line))

    def test_overpayment_beyond_the_limit_stays_open(self):
        document = self._document(1000.0)
        st_line = self._create_st_line(1001.01, partner_id=self.partner_a.id)

        st_line.set_line_bank_statement_line(document.ids)

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(self._difference_line(st_line))
        self.assertTrue(document.reconciled)

    def test_shortfall_beyond_the_limit_settles_the_document_in_part(self):
        document = self._document(1000.0)
        st_line = self._create_st_line(998.99, partner_id=self.partner_a.id)

        st_line.set_line_bank_statement_line(document.ids)

        self.assertTrue(st_line.is_reconciled)
        self.assertFalse(self._difference_line(st_line))
        self.assertAlmostEqual(document.amount_residual, 1.01)

    def test_nothing_is_written_off_without_both_accounts(self):
        self.config.payment_difference_loss_account_id = False
        document = self._document(1000.0)
        st_line = self._create_st_line(1000.40, partner_id=self.partner_a.id)

        st_line.set_line_bank_statement_line(document.ids)

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(self._difference_line(st_line))

    def test_a_foreign_currency_document_is_never_written_off(self):
        document = self._document(
            1000.0, currency_id=self.other_currency.id, invoice_date="2019-01-01"
        )
        st_line = self._create_st_line(
            document.amount_residual + 0.40, partner_id=self.partner_a.id
        )

        st_line.set_line_bank_statement_line(document.ids)

        self.assertFalse(
            self._difference_line(st_line),
            "what a rate leaves over is an exchange matter, not a rounding",
        )

    def test_the_difference_closes_over_several_matches(self):
        first = self._document(500.0)
        second = self._document(500.0)
        st_line = self._create_st_line(1000.40, partner_id=self.partner_a.id)

        st_line.set_line_bank_statement_line(first.ids)
        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(self._difference_line(st_line))
        st_line.set_line_bank_statement_line(second.ids)

        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(self._difference_line(st_line).balance, -0.40)

    def test_automatic_matching_settles_a_document_within_the_limit(self):
        document = self._document(2226.40, move_type="in_invoice")
        other = self._document(990.00, move_type="in_invoice")
        st_line = self._create_st_line(-2226.00, partner_id=self.partner_a.id)

        st_line._try_auto_reconcile_statement_lines()

        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(document.reconciled)
        self.assertFalse(other.reconciled)
        self.assertEqual(self._difference_line(st_line).account_id, self.gain_account)

    def test_automatic_matching_leaves_a_document_beyond_the_limit(self):
        document = self._document(2230.00, move_type="in_invoice")
        st_line = self._create_st_line(-2226.00, partner_id=self.partner_a.id)

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(document.reconciled)
