from odoo import fields, models
from odoo.tools import SQL, frozendict


class BudgetReport(models.Model):
    _name = "budget.report"
    _inherit = ["mixin.analytic.plan.fields"]
    _description = "Budget Report"
    _auto = False
    _depends = frozendict(
        {
            "account.account": ["account_type"],
            "account.analytic.line": [
                "account_id",
                "amount",
                "category",
                "company_id",
                "date",
                "general_account_id",
                "name",
                "user_id",
            ],
            "account.move": ["move_type"],
            "account.move.line": [
                "move_id",
                "parent_state",
                "product_uom_id",
                "quantity",
            ],
            "budget.analytic": [
                "budget_type",
                "company_id",
                "date_from",
                "date_to",
                "name",
            ],
            "budget.line": ["account_id", "budget_amount", "budget_analytic_id"],
            "uom.uom": ["factor"],
        }
    )
    _order = False

    date = fields.Date()
    res_model = fields.Char(
        string="Model",
        readonly=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Document",
        readonly=True,
    )
    description = fields.Char(readonly=True)
    company_id = fields.Many2one(
        comodel_name="res.company",
        readonly=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        readonly=True,
    )
    line_type = fields.Selection(
        selection=[("budget", "Budget"), ("achieved", "Achieved")],
        string="Type",
        readonly=True,
    )
    budget = fields.Float(readonly=True)
    achieved = fields.Float(readonly=True)
    budget_analytic_id = fields.Many2one(
        comodel_name="budget.analytic",
        readonly=True,
    )
    budget_line_id = fields.Many2one(
        comodel_name="budget.line",
        readonly=True,
    )

    def _get_bl_query(self, plan_fnames):
        budget_line_ids = self.env.context.get("budget_report_budget_line_ids")
        return SQL(
            """
            SELECT CONCAT('bl', bl.id::TEXT) AS id,
                   bl.budget_analytic_id AS budget_analytic_id,
                   bl.id AS budget_line_id,
                   'budget.analytic' AS res_model,
                   bl.budget_analytic_id AS res_id,
                   ba.date_from AS date,
                   ba.name AS description,
                   ba.company_id AS company_id,
                   NULL AS user_id,
                   'budget' AS line_type,
                   bl.budget_amount AS budget,
                   0 AS committed,  -- used in `account_budget_purchase`
                   0 AS achieved,
                   %(plan_fields)s
              FROM budget_line bl
              JOIN budget_analytic ba ON ba.id = bl.budget_analytic_id
              %(budget_line_ids_condition)s
            """,
            plan_fields=SQL(", ").join(
                self.env["budget.line"]._field_to_sql("bl", fname)
                for fname in plan_fnames
            ),
            budget_line_ids_condition=SQL(
                "WHERE bl.id = ANY(%(budget_line_ids)s)",
                budget_line_ids=budget_line_ids,
            )
            if budget_line_ids
            else SQL(""),
        )

    def _get_aal_query(self, plan_fnames):
        budget_line_ids = self.env.context.get("budget_report_budget_line_ids")
        analytic_line_ids = self._get_scoped_analytic_line_ids()
        return SQL(
            """
            SELECT CONCAT('aal', aal.id::TEXT, '-', COALESCE(bl.id, 0)::TEXT) AS id,
                   bl.budget_analytic_id AS budget_analytic_id,
                   bl.id AS budget_line_id,
                   'account.analytic.line' AS res_model,
                   aal.id AS res_id,
                   aal.date AS date,
                   aal.name AS description,
                   aal.company_id AS company_id,
                   aal.user_id AS user_id,
                   'achieved' AS line_type,
                   0 AS budget,
                   aal.amount * CASE WHEN ba.budget_type = 'expense' THEN -1 ELSE 1 END AS committed,  -- used in `account_budget_purchase`
                   aal.amount * CASE WHEN ba.budget_type = 'expense' THEN -1 ELSE 1 END AS achieved,
                   %(analytic_fields)s
              FROM account_analytic_line aal
         LEFT JOIN (budget_line bl
                    JOIN budget_analytic ba ON ba.id = bl.budget_analytic_id)
                ON (ba.company_id IS NULL OR aal.company_id = ba.company_id)
               AND aal.date >= ba.date_from
               AND aal.date <= ba.date_to
               AND %(condition)s
         LEFT JOIN account_account aa ON aa.id = aal.general_account_id
             WHERE CASE
                       WHEN ba.budget_type = 'expense' THEN (
                           SPLIT_PART(aa.account_type, '_', 1) = 'expense'
                           OR aa.account_type IN ('asset_fixed', 'asset_non_current')
                           OR (aa.account_type IS NULL AND aal.category NOT IN ('invoice', 'other'))
                           OR (aa.account_type IS NULL AND aal.category = 'other' AND aal.amount < 0)
                       )
                       WHEN ba.budget_type = 'revenue' THEN (
                           SPLIT_PART(aa.account_type, '_', 1) = 'income'
                           OR (aa.account_type IS NULL AND aal.category = 'other' AND aal.amount > 0)
                       )
                       ELSE TRUE
                   END
                   AND (
                       SPLIT_PART(aa.account_type, '_', 1) IN ('income', 'expense')
                       -- capex spends the budget that funded it, so the two
                       -- long-lived asset types belong here. `asset_current`
                       -- does not: it is the inventory leg of the anglo-saxon
                       -- COGS pair, which carries the same analytic
                       -- distribution as its expense leg with the opposite
                       -- balance, and counting both cancels the cost out.
                       OR aa.account_type IN ('asset_fixed', 'asset_non_current')
                       OR aa.account_type IS NULL
                   )
                   %(budget_line_ids_condition)s
                   %(analytic_line_ids_condition)s
            """,
            analytic_fields=SQL(", ").join(
                self.env["account.analytic.line"]._field_to_sql("aal", fname)
                for fname in plan_fnames
            ),
            condition=SQL(
                "%s AND %s",
                SQL(" AND ").join(
                    SQL(
                        "(%(bl)s IS NULL OR %(aal)s = %(bl)s)",
                        bl=self.env["budget.line"]._field_to_sql("bl", fname),
                        aal=self.env["account.analytic.line"]._field_to_sql(
                            "aal", fname
                        ),
                    )
                    for fname in plan_fnames
                ),
                SQL(
                    "(%s)",
                    SQL(" OR ").join(
                        SQL(
                            "%s IS NOT NULL",
                            self.env["budget.line"]._field_to_sql("bl", fname),
                        )
                        for fname in plan_fnames
                    ),
                ),
            ),
            budget_line_ids_condition=SQL(
                "AND bl.id = ANY(%(budget_line_ids)s)",
                budget_line_ids=budget_line_ids,
            )
            if budget_line_ids
            else SQL(""),
            analytic_line_ids_condition=SQL(
                "AND aal.id = ANY(%(analytic_line_ids)s)",
                analytic_line_ids=analytic_line_ids,
            )
            if analytic_line_ids is not None
            else SQL(""),
        )

    def _get_scoped_analytic_line_ids(self):
        analytic_line_ids = self.env.context.get("budget_report_analytic_line_ids")
        return None if analytic_line_ids is None else list(analytic_line_ids)

    @property
    def _table_query(self):
        self.env["account.account"].flush_model()
        self.env["budget.analytic"].flush_model()
        self.env["budget.line"].flush_model()
        self.env["account.analytic.line"].flush_model()
        project_plan, other_plans = self.env["account.analytic.plan"]._get_all_plans()
        plan_fnames = [
            fname
            for plan in project_plan | other_plans
            if (fname := plan._column_name()) in self
        ]
        if self._get_scoped_analytic_line_ids() is not None:
            return self._get_aal_query(plan_fnames)
        return SQL(
            "%s UNION ALL %s",
            self._get_bl_query(plan_fnames),
            self._get_aal_query(plan_fnames),
        )

    def action_view_reference(self):
        self.check_singleton()
        if self.res_model == "account.analytic.line":
            analytical_line = self.env["account.analytic.line"].browse(self.res_id)
            if analytical_line.move_line_id:
                return analytical_line.move_line_id.action_view_business_doc()
        return {
            "type": "ir.actions.act_window",
            "res_model": self.res_model,
            "view_mode": "form",
            "res_id": self.res_id,
        }
