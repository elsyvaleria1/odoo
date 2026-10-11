from odoo import api, fields, models


class BudgetLine(models.Model):
    _inherit = "budget.line"

    committed_amount = fields.Monetary(
        string="Committed",
        compute="_compute_achieved",
        help="Already Billed amount + Confirmed purchase orders.",
    )
    committed_percentage = fields.Float(
        string="Committed (%)",
        compute="_compute_achieved",
        aggregator="avg",
    )

    def _get_report_aggregates(self) -> dict:
        return {**super()._get_report_aggregates(), "committed_amount": "committed"}

    @api.model
    def _invalidate_budget_cache(self) -> None:
        super()._invalidate_budget_cache()
        self.env["purchase.order.line"].invalidate_model(
            ["budget_line_ids", "is_above_budget"]
        )
        self.env["purchase.order"].invalidate_model(["is_above_budget"])
