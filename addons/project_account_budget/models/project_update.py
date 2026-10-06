from odoo import api, models


class ProjectUpdate(models.Model):
    _inherit = "project.update"

    @api.model
    def _prepare_update_rendering_context(self, project):
        vals = super()._prepare_update_rendering_context(project)
        if project.account_id and self.env.user.has_group(
            "account.group_account_readonly"
        ):
            budget_items = project._get_budget_items(with_action=False)
            budgets = {
                "data": [],
                "total": {
                    "allocated": 0.0,
                    "spent": 0.0,
                },
            }
            if budget_items:
                budgets = {
                    "data": budget_items["data"],
                    "total": budget_items["total"],
                }
            for budget in budgets["data"]:
                budget["progress"] = budget["allocated"] and (
                    budget["spent"] - budget["allocated"]
                ) / abs(budget["allocated"])
            vals["show_activities"] = bool(project.total_budget_amount) or vals.get(
                "show_activities", False
            )
            budget = project.total_budget_amount
            cost = -budget_items["total"]["spent"] if budget_items else 0
            vals["budget"] = {
                "percentage": round(
                    (cost / budget) * 100 if budget != 0 and cost else 0, 0
                ),
                "data": budgets["data"],
                "total": budgets["total"],
                "remaining_budget_percentage": round(
                    ((budget - cost) / budget) * 100 if budget != 0 else 0, 0
                ),
            }
        return vals
