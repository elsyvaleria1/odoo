from itertools import product
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import TestAccountBudgetCommon


@tagged("post_install", "-at_install")
class TestAccountBudget(TestAccountBudgetCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.analytic_plan_empty = cls.env["account.analytic.plan"].create(
            {"name": "Empty plan"}
        )

    def test_account_budget(self):

        budget = self.budget_analytic_revenue

        self.assertRecordValues(budget, [{"state": "draft"}])

        budget.action_budget_confirm()

        self.assertRecordValues(budget, [{"state": "confirmed"}])

        budget.action_budget_confirm()

        self.assertRecordValues(budget, [{"state": "confirmed"}])

        budget.action_create_revision()

        revised_budget = self.env["budget.analytic"].search(
            [("parent_id", "=", budget.id)]
        )
        self.assertTrue(revised_budget, "The revised budget should have been created")

        revised_budget.action_budget_confirm()

        self.assertRecordValues(revised_budget, [{"state": "confirmed"}])
        self.assertRecordValues(budget, [{"state": "revised"}])

        revised_budget.action_budget_done()

        self.assertRecordValues(revised_budget, [{"state": "done"}])

    def test_budget_split(self):
        res = (
            self.env["wizard.budget.analytic.create"]
            .create(
                {
                    "date_from": "2019-01-01",
                    "date_to": "2019-12-31",
                    "period": "month",
                    "analytical_plan_ids": [
                        (
                            6,
                            0,
                            self.analytic_plan_projects.ids
                            + self.analytic_plan_departments.ids,
                        )
                    ],
                }
            )
            .action_budget_split()
        )
        self.assertTrue(
            res.get("domain"),
            "The budget split wizard should have created and returned a domain of budget.line records",
        )
        budget_lines = self.env["budget.line"].search(res.get("domain"))
        account_dict = {
            rec._column_name(): rec.account_ids.ids
            for rec in self.analytic_plan_projects + self.analytic_plan_departments
        }
        account_combinations = [
            dict(zip(account_dict.keys(), combination, strict=True))
            for combination in product(*account_dict.values())
        ]
        self.assertEqual(len(budget_lines), 12 * len(account_combinations))
        for line, combination in zip(
            budget_lines, account_combinations * 12, strict=True
        ):
            for column in combination:
                self.assertEqual(
                    line[column].id,
                    combination[column],
                    "The budget line should have the correct accounts set",
                )

    @freeze_time("2024-01-15 14:30:00")
    def test_revised_budget_name_generation(self):
        budget = self.budget_analytic_revenue
        budget.action_budget_confirm()

        revised_budget = budget.action_create_revision()
        revised_budget = self.env["budget.analytic"].browse(revised_budget["res_id"])

        expected_name = f"{budget.name} - REV(2024-01-15 14:30)"
        self.assertEqual(revised_budget.name, expected_name)

    def _split_wizard(self, **values):
        return self.env["wizard.budget.analytic.create"].create(
            {
                "date_from": "2019-01-01",
                "date_to": "2019-12-31",
                "period": "month",
                "analytical_plan_ids": [(6, 0, self.analytic_plan_projects.ids)],
                **values,
            }
        )

    def test_budget_split_keeps_the_trailing_partial_period(self):
        wizard = self._split_wizard(date_to="2019-12-15")
        lines = self.env["budget.line"].search(wizard.action_budget_split()["domain"])
        budgets = lines.budget_analytic_id.sorted("date_from")
        self.assertEqual(len(budgets), 12, "December must not be dropped")
        self.assertEqual(budgets[-1].date_from, fields.Date.to_date("2019-12-01"))
        self.assertEqual(
            budgets[-1].date_to,
            fields.Date.to_date("2019-12-15"),
            "the last period is clamped to the requested end date",
        )

    def test_budget_split_from_a_month_end_neither_drifts_nor_leaves_gaps(self):
        wizard = self._split_wizard(date_from="2024-01-31", date_to="2024-05-31")
        self.assertEqual(
            [
                (start.isoformat(), end.isoformat())
                for _name, start, end in wizard._get_periods()
            ],
            [
                ("2024-01-31", "2024-02-28"),
                ("2024-02-29", "2024-03-30"),
                ("2024-03-31", "2024-04-29"),
                ("2024-04-30", "2024-05-30"),
                ("2024-05-31", "2024-05-31"),
            ],
        )

    def test_budget_split_reaches_the_requested_end_date(self):
        wizard = self._split_wizard(date_from="2023-01-29", date_to="2023-03-28")
        self.assertEqual(
            [
                (start.isoformat(), end.isoformat())
                for _name, start, end in wizard._get_periods()
            ],
            [("2023-01-29", "2023-02-27"), ("2023-02-28", "2023-03-28")],
        )

    def test_budget_split_rejects_a_plan_without_accounts(self):
        wizard = self._split_wizard(
            analytical_plan_ids=[(6, 0, self.analytic_plan_empty.ids)], period="year"
        )
        with self.assertRaises(UserError):
            wizard.action_budget_split()

    def test_budget_split_refuses_an_unbounded_cartesian_product(self):
        wizard = self._split_wizard(
            analytical_plan_ids=[
                (
                    6,
                    0,
                    (self.analytic_plan_projects + self.analytic_plan_departments).ids,
                )
            ]
        )
        with patch.object(type(wizard), "MAX_GENERATED_LINES", 10):
            with self.assertRaises(UserError):
                wizard.action_budget_split()
        self.assertTrue(wizard.action_budget_split()["domain"])

    def test_budget_split_honours_the_budget_type(self):
        wizard = self._split_wizard(period="year", budget_type="revenue")
        lines = self.env["budget.line"].search(wizard.action_budget_split()["domain"])
        self.assertEqual(lines.budget_analytic_id.mapped("budget_type"), ["revenue"])

    def test_budget_split_rejects_inverted_dates(self):
        with self.assertRaises(ValidationError):
            self._split_wizard(date_from="2019-12-31", date_to="2019-01-01")
