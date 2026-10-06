from datetime import date
from decimal import Decimal

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestLoanComputeWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loan = cls.env["account.loan"].create({"name": "Machinery Loan"})

    def _wizard(self, **values):
        return self.env["wizard.account.loan.create.schedule"].create(
            {
                "loan_id": self.loan.id,
                "loan_amount": 12000.0,
                "interest_rate": 12.0,
                "loan_term": 1,
                "start_date": date(2026, 1, 1),
                "first_payment_date": date(2026, 2, 1),
                **values,
            }
        )

    def test_validation_rejects_invalid_inputs(self):
        """The guards must hold on write, not only through the onchange."""
        cases = [
            ("negative amount", {"loan_amount": -1}),
            ("rate above 100%", {"interest_rate": 101}),
            ("negative rate", {"interest_rate": -1}),
            ("negative term", {"loan_term": -2}),
            ("zero term", {"loan_term": 0}),
            (
                "first payment beyond the term",
                {
                    "payment_end_of_month": "at_anniversary",
                    "loan_term": 1,
                    "start_date": date(2026, 1, 1),
                    "first_payment_date": date(2027, 6, 1),
                },
            ),
        ]
        for label, values in cases:
            with self.subTest(label), self.assertRaises(ValidationError):
                self._wizard(**values)

    def test_first_payment_date_is_ignored_at_end_of_month(self):
        """It is hidden in that mode, so it must not be able to block the wizard."""
        wizard = self._wizard(loan_term=1, first_payment_date=date(2027, 6, 1))
        self.assertTrue(wizard._get_loan_payment_schedule())

    def test_schedule_repays_exactly(self):
        """The principals must sum to the amount borrowed, to the cent."""
        for amount, rate, term in [
            (12000.0, 12.0, 1),
            (10000.0, 0.0, 1),
            (1000.0, 1.0, 15),
            (777.77, 12.0, 15),
            (250000.0, 3.75, 20),
        ]:
            with self.subTest(amount=amount, rate=rate, term=term):
                wizard = self._wizard(
                    loan_amount=amount, interest_rate=rate, loan_term=term
                )
                schedule = wizard._get_loan_payment_schedule()
                self.assertEqual(len(schedule), term * 12)
                self.assertEqual(
                    sum(payment.principal for payment in schedule),
                    Decimal(str(amount)),
                    "the schedule must repay the loan exactly",
                )
                self.assertEqual(schedule[-1].balance, 0)
                self.assertTrue(all(p.principal >= 0 for p in schedule))

    def test_balance_never_grows(self):
        """A high rate must not silently turn into negative amortization."""
        schedule = self._wizard(
            loan_amount=250000.0, interest_rate=19.99, loan_term=20
        )._get_loan_payment_schedule()
        balances = [payment.balance for payment in schedule]
        self.assertEqual(balances, sorted(balances, reverse=True))

    def test_interest_rate_keeps_its_precision(self):
        def total(rate):
            wizard = self._wizard(
                loan_amount=100000.0, interest_rate=rate, loan_term=20
            )
            return sum(p.interest for p in wizard._get_loan_payment_schedule())

        self.assertNotEqual(total(4.567), total(4.57))

    def test_schedule_dates_are_dates(self):
        """pyloan returned midnight datetimes, which format_date shifts by timezone."""
        schedule = self._wizard()._get_loan_payment_schedule()
        self.assertTrue(all(type(p.date) is date for p in schedule))

    def test_preview_lists_the_whole_schedule(self):
        wizard = self._wizard()
        schedule = wizard._get_loan_payment_schedule()
        preview = wizard.preview_line_ids
        self.assertEqual(len(preview), len(schedule))
        self.assertEqual(preview[0].date, schedule[0].date)
        self.assertEqual(preview[-1].date, schedule[-1].date)
        self.assertEqual(preview[-1].balance, 0.0)
        self.assertEqual(
            sum(preview.mapped("principal")), float(sum(p.principal for p in schedule))
        )
        self.assertTrue(
            all(line.payment == line.principal + line.interest for line in preview)
        )

    def test_preview_matches_what_action_save_stores(self):
        """The preview is the schedule, not a second rendering of it."""
        wizard = self._wizard()
        previewed = [(line.date, line.principal) for line in wizard.preview_line_ids]
        wizard.action_save()
        stored = [(line.date, line.principal) for line in self.loan.line_ids]
        self.assertEqual(previewed, stored)

    def test_preview_blank_without_amount(self):
        self.assertFalse(self._wizard(loan_amount=0).preview_line_ids)

    def test_action_save_materializes_lines_and_totals(self):
        wizard = self._wizard()
        wizard.action_save()
        self.assertEqual(len(self.loan.line_ids), 12)
        self.assertEqual(self.loan.amount_borrowed, 12000.0)
        self.assertEqual(self.loan.duration, 12)
        self.assertEqual(self.loan.date, date(2026, 1, 1))
        self.assertEqual(self.loan.interest, sum(self.loan.line_ids.mapped("interest")))
        self.assertEqual(self.loan.amount_borrowed_difference, 0.0)
        self.assertEqual(self.loan.interest_difference, 0.0)
