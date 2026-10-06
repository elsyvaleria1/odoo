from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _is_reorder_allowed(self) -> bool:
        if self.recurring_invoice:
            return False
        return super()._is_reorder_allowed()
