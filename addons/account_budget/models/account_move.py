from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    budget_analytic_ids = fields.Many2many(
        comodel_name="budget.analytic",
        string="Budgets",
        compute="_compute_budget_analytic_ids",
        groups="account.group_account_readonly",
    )

    @api.depends("line_ids.analytic_line_ids")
    def _compute_budget_analytic_ids(self) -> None:
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
