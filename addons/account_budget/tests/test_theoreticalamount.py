from freezegun import freeze_time

from odoo.tests import tagged

from .common import TestAccountBudgetCommon


@tagged("post_install", "-at_install")
class TestTheoreticalAmount(TestAccountBudgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.budget_analytic = cls.env["budget.analytic"].create(
            {
                "name": "test budget name",
                "date_from": "2018-01-01",
                "date_to": "2018-12-31",
            }
        )

    def assertTheoreticalAmountAt(self, budget_line, frozen_date, expected_amount):
        with freeze_time(frozen_date):
            self.assertRecordValues(
                budget_line, [{"theoretical_amount": expected_amount}]
            )
            budget_line.invalidate_model(["theoretical_amount"])

    def test_aggregates(self):
        model = self.env["budget.line"]
        field_names = [
            "achieved_amount",
            "theoretical_amount",
            "theoretical_percentage",
        ]
        self.assertEqual(
            model.fields_get(field_names, ["aggregator"]),
            {
                "achieved_amount": {"aggregator": "sum"},
                "theoretical_amount": {"aggregator": "sum"},
                "theoretical_percentage": {"aggregator": "avg"},
            },
            f"Fields {', '.join(map(repr, field_names))} must be flagged as aggregatable.",
        )

    def _line(self, budget, amount):
        return self.env["budget.line"].create(
            {
                "budget_analytic_id": budget.id,
                "date_from": budget.date_from,
                "date_to": budget.date_to,
                "budget_amount": amount,
                self.project_column_name: self.analytic_account_partner_a.id,
            }
        )

    def test_theoretical_amount(self):
        line = self._line(self.budget_analytic, 365)

        self.assertTheoreticalAmountAt(line, "2018-01-01", 1.0)
        self.assertTheoreticalAmountAt(line, "2018-01-02", 2.0)
        self.assertTheoreticalAmountAt(line, "2018-01-03", 3.0)
        self.assertTheoreticalAmountAt(line, "2018-01-11", 11.0)
        self.assertTheoreticalAmountAt(line, "2018-02-20", 51.0)
        self.assertTheoreticalAmountAt(line, "2018-12-31", 365.0)

    @freeze_time("2018-06-15")
    def test_nothing_is_theoretically_spent_before_the_period_opens(self):
        future = self.env["budget.analytic"].create(
            {"name": "next year", "date_from": "2019-01-01", "date_to": "2019-12-31"}
        )
        self.assertRecordValues(
            self._line(future, 365),
            [{"theoretical_amount": 0.0, "theoretical_percentage": 0.0}],
        )

        one_day = self.env["budget.analytic"].create(
            {
                "name": "one day, later",
                "date_from": "2018-12-01",
                "date_to": "2018-12-01",
            }
        )
        self.assertRecordValues(
            self._line(one_day, 100),
            [{"theoretical_amount": 0.0, "theoretical_percentage": 0.0}],
        )

    @freeze_time("2018-06-15")
    def test_the_first_day_of_a_period_still_counts_as_one_day(self):
        opening = self.env["budget.analytic"].create(
            {"name": "opens today", "date_from": "2018-06-15", "date_to": "2019-06-14"}
        )
        self.assertRecordValues(self._line(opening, 365), [{"theoretical_amount": 1.0}])
        today_only = self.env["budget.analytic"].create(
            {"name": "today only", "date_from": "2018-06-15", "date_to": "2018-06-15"}
        )
        self.assertRecordValues(
            self._line(today_only, 100), [{"theoretical_amount": 100.0}]
        )
