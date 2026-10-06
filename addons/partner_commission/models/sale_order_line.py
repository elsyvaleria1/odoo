from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_domain_purchase_order_line_additional(self) -> list:
        if self.order_id.referrer_id:
            return []
        return super()._get_domain_purchase_order_line_additional()
