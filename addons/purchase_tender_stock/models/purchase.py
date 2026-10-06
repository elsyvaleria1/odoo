from odoo import api, fields, models


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    on_time_rate_perc = fields.Float(
        string="OTD",
        compute="_compute_on_time_rate_perc",
        groups="purchase.group_purchase_user",
    )

    @api.depends("on_time_rate")
    def _compute_on_time_rate_perc(self) -> None:
        for order in self:
            order.on_time_rate_perc = (
                order.on_time_rate / 100 if order.on_time_rate >= 0 else -1
            )


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    on_time_rate_perc = fields.Float(
        related="order_id.on_time_rate_perc",
        string="OTD",
    )
