from collections import defaultdict

from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    is_above_budget = fields.Boolean(compute="_compute_is_above_budget")
    is_analytic = fields.Boolean(compute="_compute_is_analytic")

    @api.depends("line_ids.analytic_distribution")
    def _compute_is_analytic(self) -> None:
        for order in self:
            order.is_analytic = any(order.line_ids.mapped("analytic_distribution"))

    @api.depends(
        "line_ids.budget_line_ids",
        "line_ids.price_subtotal",
        "line_ids.price_unit",
        "line_ids.product_qty",
        "line_ids.qty_invoiced",
        "state",
    )
    def _compute_is_above_budget(self) -> None:
        for order in self:
            # Scoped per budget.line id, not summed order-wide: several lines
            # can legitimately share one budget (their contributions must add
            # up), but a line's uncommitted amount must never count against a
            # budget none of its own budget_line_ids point to.
            uncommitted_by_budget_id = defaultdict(float)
            for line in order.line_ids:
                if not line.budget_line_ids:
                    continue
                uncommitted = line._get_uncommitted_amount()
                for budget in line.budget_line_ids:
                    uncommitted_by_budget_id[budget.id] += uncommitted
            order.is_above_budget = any(
                budget.committed_amount + uncommitted_by_budget_id[budget.id]
                > budget.budget_amount
                for budget in order.line_ids.mapped("budget_line_ids")
            )

    def action_budget(self):
        self.check_singleton()
        analytic_account_ids = [
            int(account)
            for line in self.line_ids
            for account_ids in (line.analytic_distribution or {})
            for account in account_ids.split(",")
        ]
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "account_budget.budget_report_action"
        )
        action["domain"] = [
            ("auto_account_id", "in", analytic_account_ids),
            ("budget_analytic_id.budget_type", "!=", "revenue"),
        ]
        return action
