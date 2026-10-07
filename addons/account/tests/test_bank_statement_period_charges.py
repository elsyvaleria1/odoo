from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.account.tests.common_reconcile import TestBankRecWidgetCommon

CHARGES = r"^(COM |IVA COM|SERV BANCA)"


@tagged("post_install", "-at_install")
class TestBankStatementPeriodCharges(TestBankRecWidgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank = cls.env["res.partner"].create({"name": "The Bank"})
        cls.journal = cls.company_data["default_journal_bank"]
        cls.journal.write(
            {"bank_charges_partner_id": cls.bank.id, "bank_charges_pattern": CHARGES}
        )

    def _charges(self, date="2019-03-04"):
        return (
            self._create_st_line(
                -830.0, date=date, payment_ref="COM SERV NET CASH/0115"
            )
            | self._create_st_line(
                -132.8, date=date, payment_ref="IVA COM SERVICIOS/0115"
            )
            | self._create_st_line(
                -450.0, date=date, payment_ref="SERV BANCA INTERNET/ADMON"
            )
        )

    def _bill(self, total, invoice_date="2019-04-01", post=True):
        bill = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.bank.id,
                "invoice_date": invoice_date,
                "invoice_line_ids": [
                    {
                        "name": "bank charges",
                        "quantity": 1,
                        "price_unit": total,
                        "tax_ids": [],
                        "account_id": self.company_data["default_account_expense"].id,
                    }
                ],
            }
        )
        if post:
            bill.action_post()
        return bill

    def test_a_month_of_charges_is_settled_against_the_bank_s_bill(self):
        lines = self._charges()
        bill = self._bill(1412.8)

        lines[0]._try_auto_reconcile_statement_lines()

        self.assertTrue(all(lines.mapped("is_reconciled")))
        self.assertEqual(set(lines.mapped("auto_reconcile_rule")), {"charges"})
        self.assertEqual(bill.payment_state, "paid")

    def test_a_bill_of_another_total_is_left_to_a_person(self):
        lines = self._charges()
        self._bill(1412.81)

        lines._try_auto_reconcile_statement_lines()

        self.assertFalse(any(lines.mapped("is_reconciled")))

    def test_two_bills_of_the_total_are_left_to_a_person(self):
        lines = self._charges()
        self._bill(1412.8)
        self._bill(1412.8, invoice_date="2019-04-02")

        lines._try_auto_reconcile_statement_lines()

        self.assertFalse(any(lines.mapped("is_reconciled")))

    def test_a_draft_bill_waits_to_be_posted(self):
        lines = self._charges()
        bill = self._bill(1412.8, post=False)

        lines._try_auto_reconcile_statement_lines()
        self.assertFalse(any(lines.mapped("is_reconciled")))

        bill.action_post()
        lines._try_auto_reconcile_statement_lines()
        self.assertTrue(all(lines.mapped("is_reconciled")))

    def test_a_bill_dated_outside_the_month_s_window_is_not_its_bill(self):
        lines = self._charges()
        self._bill(1412.8, invoice_date="2019-05-20")

        lines._try_auto_reconcile_statement_lines()

        self.assertFalse(any(lines.mapped("is_reconciled")))

    def test_a_line_that_is_not_a_charge_stays_out_of_the_month(self):
        lines = self._charges()
        other = self._create_st_line(
            -99.0, date="2019-03-10", payment_ref="SPEI ENVIADO"
        )
        self._bill(1412.8)

        lines._try_auto_reconcile_statement_lines()

        self.assertTrue(all(lines.mapped("is_reconciled")))
        self.assertFalse(other.is_reconciled)

    def test_a_journal_naming_no_invoicer_settles_nothing_this_way(self):
        self.journal.bank_charges_partner_id = False
        lines = self._charges()
        self._bill(1412.8)

        lines._try_auto_reconcile_statement_lines()

        self.assertNotIn("charges", lines.mapped("auto_reconcile_rule"))

    def test_an_invalid_pattern_is_refused(self):
        with self.assertRaises(ValidationError):
            self.journal.bank_charges_pattern = "^(COM"
