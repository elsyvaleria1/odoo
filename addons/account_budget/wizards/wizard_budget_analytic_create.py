import math
from functools import partial
from itertools import product

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Date
from odoo.tools import date_utils, format_date


class WizardBudgetAnalyticCreate(models.TransientModel):
    _name = "wizard.budget.analytic.create"
    _description = "Budget Split Wizard"

    # every combination of accounts across the selected plans becomes a line, so
    # the count is the product of the plan sizes times the number of periods
    MAX_GENERATED_LINES = 10_000

    PERIODS = {
        "month": (relativedelta(months=1), "MMMM yyyy"),
        "quarter": (relativedelta(months=3), "QQQ yyyy"),
        "year": (relativedelta(years=1), "yyyy"),
    }

    date_from = fields.Date(
        string="Start Date",
        required=True,
    )
    date_to = fields.Date(
        string="End Date",
        required=True,
    )
    period = fields.Selection(
        selection=[("month", "Month"), ("quarter", "Quarter"), ("year", "Year")],
        default="year",
        required=True,
    )
    budget_type = fields.Selection(
        selection=[("revenue", "Revenue"), ("expense", "Expense"), ("both", "Both")],
        default="expense",
        required=True,
    )
    analytical_plan_ids = fields.Many2many(
        comodel_name="account.analytic.plan",
        string="Analytic Plans",
        required=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self) -> None:
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(
                    self.env._("The end date may not be before the starting date.")
                )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if "date_from" in fields and not defaults.get("date_from"):
            defaults["date_from"] = date_utils.start_of(
                Date.context_today(self), "year"
            )
        if "date_to" in fields and not defaults.get("date_to"):
            defaults["date_to"] = date_utils.end_of(Date.context_today(self), "year")
        return defaults

    def _get_periods(self):
        """The periods to cover, with the trailing partial one clamped.

        Dropping it instead would silently produce eleven budgets for a request
        spanning twelve months minus a fortnight.
        """
        step, date_format = self.PERIODS[self.period]
        name = partial(format_date, self.env, date_format=date_format)
        starts = list(date_utils.date_range(self.date_from, self.date_to, step))
        ends = [start - relativedelta(days=1) for start in starts[1:]]
        # the next start lies past date_to, so the last period ends on it
        ends.append(self.date_to)
        return [
            (name(date_from), date_from, date_to)
            for date_from, date_to in zip(starts, ends, strict=True)
        ]

    def _get_accounts_per_plan(self):
        accounts_per_plan = {
            plan._column_name(): plan.account_ids.ids
            for plan in self.analytical_plan_ids
        }
        if empty := [
            plan.display_name
            for plan in self.analytical_plan_ids
            if not plan.account_ids
        ]:
            raise UserError(
                self.env._(
                    "These analytic plans hold no account, so no budget line can "
                    "be generated: %(names)s",
                    names=", ".join(empty),
                )
            )
        return accounts_per_plan

    def _get_account_combinations(self, accounts_per_plan) -> list:
        return [
            dict(zip(accounts_per_plan, combination, strict=True))
            for combination in product(*accounts_per_plan.values())
        ]

    def action_budget_split(self) -> dict:
        self.check_singleton()
        periods = self._get_periods()
        accounts_per_plan = self._get_accounts_per_plan()
        combination_count = math.prod(len(v) for v in accounts_per_plan.values())
        total = len(periods) * combination_count
        if total > self.MAX_GENERATED_LINES:
            raise UserError(
                self.env._(
                    "This would generate %(total)s budget lines "
                    "(%(periods)s periods x %(combinations)s account combinations), "
                    "over the %(maximum)s limit. Select fewer analytic plans, a "
                    "shorter range or a longer period.",
                    total=total,
                    periods=len(periods),
                    combinations=combination_count,
                    maximum=self.MAX_GENERATED_LINES,
                )
            )
        combinations = self._get_account_combinations(accounts_per_plan)
        budget_lines = [Command.create(combination) for combination in combinations]
        budgets = self.env["budget.analytic"].create(
            [
                {
                    "name": self.env._("Budget %s", label),
                    "date_from": date_from,
                    "date_to": date_to,
                    "budget_type": self.budget_type,
                    "budget_line_ids": budget_lines,
                }
                for label, date_from, date_to in periods
            ]
        )
        return {
            "name": self.env._("Budgets"),
            "view_mode": "list",
            "res_model": "budget.line",
            "type": "ir.actions.act_window",
            "domain": [("id", "in", budgets.budget_line_ids.ids)],
            "context": {"group_by": "budget_analytic_id"},
        }
