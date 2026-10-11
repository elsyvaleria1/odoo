import datetime
import itertools
from decimal import Decimal

from odoo.tests.common import BaseCase

from odoo.addons.account_loans.lib import amortization

START = datetime.date(2024, 1, 1)


class TestAmortization(BaseCase):

    def test_repays_the_loan_exactly_across_the_grid(self):
        amounts = [1000.0, 9999.99, 12345.67, 100000.0, 250000.0, 777.77]
        rates = [0.0, 0.01, 1.0, 3.75, 12.0, 19.99]
        terms = [1, 2, 5, 15, 20]
        for amount, rate, term in itertools.product(amounts, rates, terms):
            schedule = amortization.generate(amount, rate, term, START)
            with self.subTest(amount=amount, rate=rate, term=term):
                self.assertEqual(
                    sum(p.principal for p in schedule), Decimal(str(amount))
                )
                self.assertEqual(schedule[-1].balance, 0)
                self.assertTrue(all(p.principal >= 0 for p in schedule))
                balances = [p.balance for p in schedule]
                self.assertEqual(balances, sorted(balances, reverse=True))

    def test_rejects_invalid_input(self):
        for label, kwargs in [
            ("zero term", {"years": 0}),
            ("negative term", {"years": -1}),
            ("negative amount", {"amount": -1.0}),
            ("rate above 100", {"annual_rate": 101.0}),
            ("negative rate", {"annual_rate": -0.1}),
            ("unknown convention", {"convention": "nonsense"}),
            (
                "first payment before start",
                {"first_payment_date": datetime.date(2023, 1, 1)},
            ),
        ]:
            arguments = {
                "amount": 1000.0,
                "annual_rate": 5.0,
                "years": 1,
                "start_date": START,
            }
            arguments.update(kwargs)
            with self.subTest(label), self.assertRaises(amortization.ScheduleError):
                amortization.generate(**arguments)

    def test_dates_are_plain_dates_at_month_end(self):
        schedule = amortization.generate(12000.0, 5.0, 1, datetime.date(2024, 1, 15))
        self.assertTrue(all(type(p.date) is datetime.date for p in schedule))
        self.assertEqual(schedule[0].date, datetime.date(2024, 1, 31))
        self.assertEqual(schedule[1].date, datetime.date(2024, 2, 29))
        self.assertEqual(schedule[-1].date, datetime.date(2024, 12, 31))

    def test_anniversary_dates_follow_the_first_payment(self):
        schedule = amortization.generate(
            12000.0,
            5.0,
            1,
            datetime.date(2024, 1, 15),
            first_payment_date=datetime.date(2024, 3, 10),
            end_of_month=False,
        )
        self.assertEqual(schedule[0].date, datetime.date(2024, 3, 10))
        self.assertEqual(schedule[1].date, datetime.date(2024, 4, 10))

    def test_rate_precision_is_preserved(self):
        def total(rate):
            return sum(
                p.interest for p in amortization.generate(100000.0, rate, 20, START)
            )

        self.assertNotEqual(total(4.567), total(4.57))
        self.assertLess(total(4.567), total(4.57))

    def test_zero_rate_costs_nothing(self):
        schedule = amortization.generate(12000.0, 0.0, 1, START)
        self.assertEqual(sum(p.interest for p in schedule), 0)
        self.assertTrue(all(p.principal == Decimal("1000.00") for p in schedule))

    def test_every_day_count_convention_produces_a_schedule(self):
        for convention in amortization.DAY_COUNT_CONVENTIONS:
            with self.subTest(convention):
                schedule = amortization.generate(
                    100000.0, 5.0, 3, START, convention=convention
                )
                self.assertEqual(sum(p.principal for p in schedule), Decimal(100000))
                self.assertGreater(sum(p.interest for p in schedule), 0)

    def test_day_count_conventions_against_known_values(self):
        day = datetime.date
        cases = [
            ("A/A AFB", day(2024, 1, 1), day(2025, 1, 1), Decimal(1)),
            ("A/A AFB", day(2023, 1, 1), day(2026, 1, 1), Decimal(3)),
            ("A/A ISDA", day(2024, 1, 1), day(2025, 1, 1), Decimal(1)),
            ("A/A AFB", day(2024, 2, 1), day(2024, 3, 1), Decimal(29) / 366),
            ("A/A AFB", day(2023, 2, 1), day(2023, 3, 1), Decimal(28) / 365),
            ("30E/360", day(2024, 1, 31), day(2024, 2, 29), Decimal(29) / 360),
            ("A/360", day(2024, 1, 1), day(2024, 1, 31), Decimal(30) / 360),
            ("A/365F", day(2024, 1, 1), day(2024, 1, 31), Decimal(30) / 365),
        ]
        for convention, start, end, expected in cases:
            with self.subTest(convention=convention, start=start, end=end):
                self.assertEqual(
                    amortization.year_fraction(start, end, convention), expected
                )

    def test_isda_splits_across_calendar_years(self):
        fraction = amortization.year_fraction(
            datetime.date(2023, 11, 1), datetime.date(2024, 5, 1), "A/A ISDA"
        )
        self.assertEqual(fraction, Decimal(61) / 365 + Decimal(121) / 366)
