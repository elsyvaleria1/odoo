from odoo import api, models
from odoo.fields import Domain


class ProductTrace(models.Model):
    _inherit = "product.trace"

    def action_auto_assign_lots(self) -> None:
        if not (sol_id := self.env.context.get("order_line_id")):
            return

        sol = self.env["sale.order.line"].browse(sol_id)
        sol.reserved_trace_ids = (
            sol.reserved_trace_ids | self._get_available_lots(sol.product_id)
        )[: int(sol.product_uom_qty)]

    @api.model
    def _get_available_lots(self, products, location=None):
        quant_domain = Domain(
            [
                ("product_id", "in", products.ids),
                ("trace_id", "!=", False),
                ("location_id.usage", "=", "internal"),
            ]
        )
        if location:
            quant_domain &= Domain.OR(
                [
                    Domain("location_id", "=", location.id),
                    Domain("location_id", "child_of", location.id),
                ]
            )

        return self.env["stock.quant"].search(quant_domain).trace_id

    @api.model
    def _get_lots_in_rent(self, product):
        return self._get_available_lots(product, self.env.company.rental_loc_id)
