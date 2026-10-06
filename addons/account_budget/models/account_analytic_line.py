from odoo import api, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        self.env["budget.line"]._invalidate_budget_cache()
        return lines

    def write(self, vals):
        result = super().write(vals)
        self.env["budget.line"]._invalidate_budget_cache()
        return result

    def unlink(self):
        self.env["budget.line"]._invalidate_budget_cache()
        return super().unlink()
