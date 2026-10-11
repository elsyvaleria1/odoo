from odoo.tests import tagged

from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon


@tagged("post_install", "-at_install")
class TestBankStatementAmountAlone(TestBankRecWidgetCommon):
    def _bill(self, amount, invoice_date="2019-01-03", **kwargs):
        return self._create_invoice_line(
            "in_invoice",
            invoice_date=invoice_date,
            invoice_line_ids=[
                {
                    "price_unit": amount,
                    "account_id": self.company_data["default_account_expense"].id,
                }
            ],
            **kwargs,
        )

    def test_the_one_bill_of_an_unusual_amount_is_matched_for_review(self):
        bill = self._bill(44487.71)
        st_line = self._create_st_line(-44487.71, payment_ref="SPEI ENVIADO 0001")

        st_line._try_auto_reconcile_statement_lines()

        self.assertTrue(st_line.is_reconciled)
        self.assertTrue(bill.reconciled)
        self.assertEqual(st_line.auto_reconcile_rule, "amount_alone")
        self.assertEqual(st_line.partner_id, self.partner_a)
        self.assertFalse(
            st_line.move_id.checked,
            "a match resting on the amount alone waits for a person to review it",
        )

    def test_a_bill_waiting_to_be_posted_is_left_to_a_person(self):
        bill = self._bill(31250.4)
        bill.move_id.action_draft()
        st_line = self._create_st_line(-31250.4, payment_ref="SPEI ENVIADO 0010")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(bill.matched_debit_ids)
        self.assertEqual(bill.move_id.payment_state, "not_paid")

        bill.move_id.action_post()
        st_line._try_auto_reconcile_statement_lines()
        self.assertTrue(bill.reconciled)
        self.assertEqual(st_line.auto_reconcile_rule, "amount_alone")

    def test_a_draft_bill_of_the_same_amount_makes_it_usual(self):
        bill = self._bill(9150.0)
        self._bill(9150.0, partner_id=self.partner_b.id).move_id.action_draft()
        st_line = self._create_st_line(-9150.0, payment_ref="SPEI ENVIADO 0011")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(bill.reconciled)

    def test_an_amount_two_bills_carry_names_neither(self):
        bills = self._bill(5000.0) + self._bill(5000.0)
        st_line = self._create_st_line(-5000.0, payment_ref="SPEI ENVIADO 0002")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(any(bills.mapped("reconciled")))

    def test_a_bill_due_in_instalments_counts_by_its_total(self):
        instalments = self._bill(6100.0, partner_id=self.partner_b.id)
        self.assertGreater(
            len(instalments), 1, "partner_b's payment terms split the bill"
        )
        bill = self._bill(6100.0)
        st_line = self._create_st_line(-6100.0, payment_ref="SPEI ENVIADO 0008")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(
            st_line.is_reconciled,
            "the amount is also the total of another bill, on none of its lines",
        )
        self.assertFalse(bill.reconciled)

    def test_a_settled_bill_of_the_same_amount_still_makes_it_usual(self):
        settled = self._bill(7300.0, invoice_date="2018-06-01")
        payment = self._create_st_line(-7300.0, date="2018-06-02")
        payment.set_line_bank_statement_line(settled.ids)
        self._bill(7300.0, partner_id=self.partner_b.id)
        st_line = self._create_st_line(-7300.0, payment_ref="SPEI ENVIADO 0003")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(
            st_line.is_reconciled,
            "an amount that recurs within the year identifies no document",
        )

    def test_a_bill_dated_far_from_the_transaction_is_left_alone(self):
        bill = self._bill(8123.45, invoice_date="2018-11-20")
        st_line = self._create_st_line(-8123.45, payment_ref="SPEI ENVIADO 0004")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(bill.reconciled)

    def test_a_transfer_the_bank_sent_back_settles_nothing(self):
        bill = self._bill(7483.21)
        st_line = self._create_st_line(-7483.21, payment_ref="SPEI ENVIADO 0009")
        self._create_st_line(
            7483.21, date="2019-01-03", payment_ref="SPEI DEVUELTO 0009"
        )

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(bill.reconciled)

    def test_incoming_money_is_never_matched_on_the_amount_alone(self):
        invoice = self._create_invoice_line(
            "out_invoice",
            invoice_date="2019-01-03",
            invoice_line_ids=[
                {
                    "price_unit": 44487.71,
                    "account_id": self.company_data["default_account_revenue"].id,
                }
            ],
        )
        st_line = self._create_st_line(44487.71, payment_ref="SPEI RECIBIDO 0005")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)
        self.assertFalse(invoice.reconciled)

    def test_a_bill_in_another_currency_is_left_alone(self):
        bill = self._bill(1000.0, currency_id=self.other_currency.id)
        st_line = self._create_st_line(bill.balance, payment_ref="SPEI ENVIADO 0006")

        st_line._try_auto_reconcile_statement_lines()

        self.assertFalse(st_line.is_reconciled)

    def test_a_reviewed_match_reads_as_any_other(self):
        self._bill(44487.71)
        st_line = self._create_st_line(-44487.71, payment_ref="SPEI ENVIADO 0007")
        st_line._try_auto_reconcile_statement_lines()

        st_line.move_id.set_moves_checked()

        self.assertTrue(st_line.move_id.checked)
        self.assertTrue(st_line.is_reconciled)
        self.assertEqual(st_line.auto_reconcile_rule, "amount_alone")
