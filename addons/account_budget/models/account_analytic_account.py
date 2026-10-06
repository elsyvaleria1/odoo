from odoo import fields, models


class AccountAnalyticAccount(models.Model):
    _inherit = "account.analytic.account"

    # `auto_account_id` is computed per `analytic_plan_id`, so this o2m resolves
    # differently under different contexts and has to be cached per context too
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
        )  # patch the budget line list view
