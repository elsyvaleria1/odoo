from typing import Literal

from odoo import models


class StockForecasted_Product_Product(models.AbstractModel):
    _inherit = "stock.forecasted_product_product"

    def _get_reservation_data(self, move) -> dict | Literal[False]:
        if move.repair_id and move.repair_line_type:
            return False
        return super()._get_reservation_data(move)

    def _get_domain_product_sale(self, product_template_ids, product_ids):
        sol_domain = super()._get_domain_product_sale(product_template_ids, product_ids)
        move_domain = self._get_domain_product(product_template_ids, product_ids)
        move_domain += [
            ("repair_id", "!=", False),
            ("sale_line_id", "!=", False),
            ("repair_line_type", "=", "add"),
        ]
        sol_ids = self.env["stock.move"]._read_group(
            move_domain, aggregates=["sale_line_id:array_agg"]
        )[0][0]

        sol_domain += [("id", "not in", sol_ids)]
        return sol_domain
