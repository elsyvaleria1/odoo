from odoo import models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _get_subscription_qty_invoiced(
        self, last_invoice_date=None, next_invoice_date=None, draft=False
    ):
        result = super()._get_subscription_qty_invoiced(
            last_invoice_date, next_invoice_date, draft=draft
        )
        if draft:
            # a point-of-sale line is never a draft invoice
            return result
        for sale_line in self:
            result[sale_line.id] = result.get(sale_line.id, 0) + sum(
                (
                    self._convert_qty(sale_line, pos_line.qty, "p2s")
                    for pos_line in sale_line.sudo().pos_order_line_ids
                ),
                0,
            )
        return result
