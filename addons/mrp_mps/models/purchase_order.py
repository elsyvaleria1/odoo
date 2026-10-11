from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    date_planned_mps = fields.Datetime(
        string="Scheduled Date",
        compute="_compute_date_planned_mps",
        store=True,
        index=True,
    )

    @api.depends("line_ids.date_commitment", "date_order")
    def _compute_date_planned_mps(self) -> None:
        for order in self:
            min_date = False
            for line in order.line_ids:
                if not min_date or (
                    line.date_commitment and line.date_commitment < min_date
                ):
                    min_date = line.date_commitment
            if min_date:
                order.date_planned_mps = min_date.date()
            else:
                order.date_planned_mps = order.date_order.date()
