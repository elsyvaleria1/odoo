from odoo import api, fields, models
from odoo.fields import Domain


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    analytic_json = fields.Json(
        string="Analytic JSON",
        compute="_compute_analytic_json",
        store=True,
    )
    is_above_budget = fields.Boolean(compute="_compute_is_above_budget")
    budget_line_ids = fields.One2many(
        comodel_name="budget.line",
        string="Budget Lines",
        compute="_compute_budget_line_ids",
    )

    @api.depends("analytic_distribution")
    def _compute_analytic_json(self) -> None:
        for line in self:
            distribution = []
            for analytic_account_ids, percentage in (
                line.analytic_distribution or {}
            ).items():
                dist_dict = {"rate": float(percentage) / 100}
                for analytic_account in (
                    self.env["account.analytic.account"]
                    .browse(map(int, analytic_account_ids.split(",")))
                    .exists()
                ):
                    root_plan = analytic_account.root_plan_id
                    dist_dict[root_plan._column_name()] = analytic_account.id
                distribution.append(dist_dict)
            line.analytic_json = distribution

    @api.depends(
        "analytic_distribution",
        "product_qty",
        "qty_transferred",
        "order_id.date_order",
    )
    def _compute_budget_line_ids(self) -> None:
        def get_domains(line):
            if not self.env["budget.analytic"].has_access("read"):
                return False
            if line.analytic_json and line.product_qty - line.qty_transferred > 0:
                project_plan, other_plans = self.env[
                    "account.analytic.plan"
                ]._get_all_plans()
                plan_fnames = {
                    plan._column_name() for plan in project_plan + other_plans
                }

                domains = []
                for json in line.analytic_json:
                    domain_to_add = set(plan_fnames)
                    domain = [
                        (
                            "budget_analytic_id",
                            "any",
                            (
                                ("budget_type", "!=", "revenue"),
                                ("state", "=", "confirmed"),
                            ),
                        ),
                        ("date_from", "<=", line.order_id.date_order),
                        ("date_to", ">=", line.order_id.date_order),
                    ]
                    for key, value in json.items():
                        if key in self.env["budget.line"]._fields:
                            domain += [(key, "=", value)]
                            domain_to_add.discard(key)
                    for key in domain_to_add:
                        domain += [(key, "=", False)]
                    domains.append(tuple(domain))
                return tuple(domains)
            return False

        for domains, lines in self.grouped(get_domains).items():
            budget_lines = self.env["budget.line"]
            if domains:
                budget_lines = self.env["budget.line"].search(
                    Domain.OR(list(domain) for domain in domains)
                )
            for line in lines:
                line.budget_line_ids = budget_lines

    def _get_uncommitted_amount(self):
        self.check_singleton()
        if self.order_id.state == "done":
            return 0.0
        price_unit = (
            self.price_subtotal / self.product_qty
            if self.product_qty
            else self.price_unit
        )
        return price_unit * (self.product_qty - self.qty_invoiced)

    @api.depends(
        "budget_line_ids", "price_subtotal", "price_unit", "product_qty", "qty_invoiced"
    )
    def _compute_is_above_budget(self) -> None:
        for line in self:
            uncommitted_amount = line._get_uncommitted_amount()
            line.is_above_budget = any(
                budget.committed_amount + uncommitted_amount > budget.budget_amount
                for budget in line.budget_line_ids
            )
