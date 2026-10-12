from odoo import api, models


class BudgetAnalytic(models.Model):
    _inherit = "budget.analytic"

    @api.model_create_multi
    def create(self, vals_list):
        budgets = super().create(vals_list)
        if len(budgets) == 1 and self.env.context.get("project_update"):
            budgets.action_budget_confirm()
        return budgets
