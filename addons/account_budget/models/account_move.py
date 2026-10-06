from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    budget_analytic_ids = fields.Many2many(
        comodel_name="budget.analytic",
        string="Budgets",
        compute="_compute_budget_analytic_ids",
        # `budget.report` is readable by `group_account_readonly` and above;
        # `group_account_invoice` implies only `base.group_user`
        # (`core/addons/account/security/account_security.xml:64-70`), so an
        # invoicing-only user must not reach this field or the compute would
        # raise on them.
        groups="account.group_account_readonly",
    )

    @api.depends("line_ids.analytic_line_ids")
    def _compute_budget_analytic_ids(self) -> None:
        """Read the budgets off `budget.report` instead of re-deriving them.

        The report is already the model that decides which budget line an
        analytic entry falls under: it applies the period, the company, the
        account type against the budget type, and the guard that a budget
        line scoping no plan at all claims nothing. Re-deriving that join
        here would give the smart button its own opinion, and the button and
        the report would disagree the first time either one changed.
        """
        move_of_line = {
            line.id: move for move in self for line in move.line_ids.analytic_line_ids
        }
        budgets = dict.fromkeys(self, self.env["budget.analytic"])
        if move_of_line:
            rows = (
                self.env["budget.report"]
                .with_context(budget_report_analytic_line_ids=list(move_of_line))
                .search(
                    [
                        ("res_model", "=", "account.analytic.line"),
                        ("res_id", "in", list(move_of_line)),
                        ("budget_analytic_id", "!=", False),
                    ]
                )
            )
            for row in rows:
                move = move_of_line[row.res_id]
                budgets[move] |= row.budget_analytic_id
        for move in self:
            move.budget_analytic_ids = budgets[move]

    def action_open_budget(self):
        self.check_singleton()
        return self.budget_analytic_ids._get_records_action(name=self.env._("Budgets"))
