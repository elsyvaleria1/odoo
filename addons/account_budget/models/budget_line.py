from datetime import timedelta

from odoo import api, fields, models
from odoo.tools import SQL, Query


class BudgetLine(models.Model):
    _name = "budget.line"
    _inherit = ["mixin.analytic.plan.fields"]
    _description = "Budget Line"
    _order = "sequence, id"
    _check_company_auto = True

    PYTHON_AGGREGATORS = ("sum", "sum_currency", "avg")

    name = fields.Char(
        related="budget_analytic_id.name",
        string="Budget Name",
    )
    sequence = fields.Integer(default=10)
    budget_analytic_id = fields.Many2one(
        comodel_name="budget.analytic",
        index=True,
        required=True,
        ondelete="cascade",
    )
    date_from = fields.Date(
        related="budget_analytic_id.date_from",
        string="Start Date",
    )
    date_to = fields.Date(
        related="budget_analytic_id.date_to",
        string="End Date",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        readonly=True,
    )
    budget_amount = fields.Monetary(string="Budgeted")
    achieved_amount = fields.Monetary(
        string="Achieved",
        compute="_compute_achieved",
        help="Amount Billed/Invoiced.",
    )
    achieved_percentage = fields.Float(
        string="Achieved (%)",
        compute="_compute_achieved",
        aggregator="avg",
    )
    theoretical_amount = fields.Monetary(
        string="Theoretical",
        compute="_compute_theoretical",
        help="Amount supposed to be Billed/Invoiced, formula = (Budget Amount / Budget Days) x Budget Days Completed",
    )
    theoretical_percentage = fields.Float(
        string="Theoretical (%)",
        compute="_compute_theoretical",
        aggregator="avg",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="budget_analytic_id.company_id",
        string="Company",
        readonly=True,
    )
    is_above_budget = fields.Boolean(compute="_compute_is_above_budget")
    budget_analytic_state = fields.Selection(
        related="budget_analytic_id.state",
        string="Budget State",
        readonly=True,
    )

    @api.depends("company_id")
    def _compute_currency_id(self) -> None:
        for budget in self:
            budget.currency_id = (budget.company_id or self.env.company).currency_id

    @api.depends("achieved_amount", "budget_amount")
    def _compute_is_above_budget(self) -> None:
        for line in self:
            line.is_above_budget = line.achieved_amount > line.budget_amount

    @staticmethod
    def _percentage_fname(amount_fname) -> str:
        """`achieved_amount` -> `achieved_percentage`; the pairing every
        aggregated amount is expected to follow."""
        return f"{amount_fname.removesuffix('_amount')}_percentage"

    def _get_report_aggregates(self) -> dict:
        """Map each computed amount to the `budget.report` column feeding it.

        One `_read_group` fills them all; a module adding an amount extends this
        mapping instead of overriding the compute.
        """
        return {"achieved_amount": "achieved"}

    @api.depends(
        lambda self: [
            "budget_amount",
            "date_from",
            "date_to",
            "budget_analytic_id.budget_type",
            *self._get_plan_fnames(),
        ]
    )
    def _compute_achieved(self) -> None:
        aggregates = self._get_report_aggregates()
        grouped = {
            line: amounts
            for line, *amounts in self.env["budget.report"]
            .with_context(budget_report_budget_line_ids=self.ids)
            ._read_group(
                domain=[("budget_line_id", "in", self.ids)],
                groupby=["budget_line_id"],
                aggregates=[f"{column}:sum" for column in aggregates.values()],
            )
        }
        empty = [0.0] * len(aggregates)
        for line in self:
            for fname, amount in zip(aggregates, grouped.get(line, empty), strict=True):
                line[fname] = amount
                line[self._percentage_fname(fname)] = (
                    line.budget_amount and amount / line.budget_amount
                )

    @api.depends("date_from", "date_to", "budget_amount")
    def _compute_theoretical(self) -> None:
        today = fields.Date.context_today(self)
        for line in self:
            # before the period opens nothing is expected yet; without this the
            # clamp below floors at one day, which is the whole budget when the
            # period is one day long
            if not line.date_from or not line.date_to or today < line.date_from:
                line.theoretical_amount = 0
                line.theoretical_percentage = 0
                continue
            # One day is added since we need to include the start and end date in the computation.
            # For example, between April 1st and April 30th, the timedelta must be 30 days.
            line_timedelta = line.date_to - line.date_from + timedelta(days=1)
            elapsed_timedelta = (
                min(today, line.date_to) - line.date_from + timedelta(days=1)
            )
            line.theoretical_amount = (
                elapsed_timedelta.total_seconds() / line_timedelta.total_seconds()
            ) * line.budget_amount
            line.theoretical_percentage = line.budget_amount and (
                line.theoretical_amount / line.budget_amount
            )

    def _field_to_sql(
        self, alias: str, field_expr: str, query: (Query | None) = None
    ) -> SQL:
        if field_expr == "currency_id" and query is not None:
            # `company_id` is related to the budget and carries no column of its
            # own here -- the 1.2 migration dropped it -- so the company has to
            # be reached through the stored `budget_analytic_id`.
            budget_alias = query.left_join(
                alias, "budget_analytic_id", "budget_analytic", "id", "budget_analytic"
            )
            company_alias = query.left_join(
                budget_alias, "company_id", "res_company", "id", "company_id"
            )
            return SQL(
                "COALESCE(%(company_alias)s.currency_id, %(env_currency_id)s)",
                company_alias=SQL.identifier(company_alias),
                env_currency_id=self.env.company.currency_id.id,
            )
        return super()._field_to_sql(alias, field_expr, query)

    def _get_python_aggregated_fields(self) -> set:
        """Non-stored fields aggregated in Python rather than in SQL.

        `Field._description_aggregator` probes `_read_group_select`, so a field
        absent here advertises no aggregator and can never be a pivot measure.
        """
        return {
            *self._get_report_aggregates(),
            *map(self._percentage_fname, self._get_report_aggregates()),
            "theoretical_amount",
            "theoretical_percentage",
        }

    def _split_python_aggregate(self, aggregate_spec) -> tuple:
        field_name, _sep, operator = aggregate_spec.partition(":")
        if (
            operator in self.PYTHON_AGGREGATORS
            and field_name in self._get_python_aggregated_fields()
        ):
            return field_name, operator
        return None, None

    def _read_group_select(self, aggregate_spec, query):
        # flag the computed amounts as aggregatable and sum them from the
        # records of each group, since none of them is a stored column
        if self._split_python_aggregate(aggregate_spec)[0]:
            return super()._read_group_select("id:recordset", query)
        return super()._read_group_select(aggregate_spec, query)

    def _read_group_postprocess_aggregate(self, aggregate_spec, raw_values):
        field_name, operator = self._split_python_aggregate(aggregate_spec)
        if not field_name:
            return super()._read_group_postprocess_aggregate(aggregate_spec, raw_values)
        column = super()._read_group_postprocess_aggregate("id:recordset", raw_values)
        if operator == "sum":
            return (sum(records.mapped(field_name)) for records in column)
        if operator == "avg":
            return (
                sum(records.mapped(field_name)) / len(records) if records else 0.0
                for records in column
            )
        return (
            sum(
                record.currency_id._convert(
                    from_amount=record[field_name],
                    to_currency=self.env.company.currency_id,
                )
                for record in records
            )
            for records in column
        )

    @api.model
    def _invalidate_budget_cache(self) -> None:
        """Drop every figure derived from `budget.report`.

        The report is an SQL view, so no ORM dependency reaches its rows: both
        its own cached rows and the aggregates read out of them survive a change
        to a budget, a budget line or an analytic entry.
        """
        self.invalidate_model(
            sorted(self._get_python_aggregated_fields() | {"is_above_budget"})
        )
        self.env["budget.report"].invalidate_model()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        # `@api.constrains` only fires for fields present in `vals`, so a caller
        # omitting every plan key produced a line matching every analytic entry
        lines._check_account_id()
        self._invalidate_budget_cache()
        return lines

    def write(self, vals):
        result = super().write(vals)
        self._invalidate_budget_cache()
        return result

    def unlink(self):
        self._invalidate_budget_cache()
        return super().unlink()

    def action_view_budget_entries(self):
        self.check_singleton()
        domain = [
            ("budget_analytic_id", "=", self.budget_analytic_id.id),
            ("budget_line_id", "=", self.id),
        ]
        for fname in self._get_plan_fnames():
            if self[fname]:
                domain += [(fname, "in", self[fname].ids)]
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "account_budget.budget_report_action"
        )
        action.update(
            {
                "domain": domain,
                "views": [(False, "list"), (False, "pivot"), (False, "graph")],
            }
        )
        return action
