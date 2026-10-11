from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    budget_line_ids = fields.One2many(
        comodel_name="budget.line",
        inverse_name="auto_account_id",
        depends_context=("analytic_plan_id",),
        readonly=False,
    )

    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        return self.env["budget.line"]._patch_view(
            arch, view, view_type
        )
