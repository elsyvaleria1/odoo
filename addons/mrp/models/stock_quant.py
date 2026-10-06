from odoo import api, models
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = "stock.quant"

    @api.constrains("product_id")
    def _check_kits(self) -> None:
        if self.sudo().product_id.filtered("is_kit"):
            raise UserError(
                self.env._(
                    "You should update the components quantity instead of directly updating the quantity of the kit product."
                )
            )

    def _is_product_bypass_required(
        self,
        product_id=False,
        location_id=False,
        reserved_quantity=0,
        trace_id=False,
        package_id=False,
        owner_id=False,
    ) -> bool:
        return bool(
            super()._is_product_bypass_required(
                product_id,
                location_id,
                reserved_quantity,
                trace_id,
                package_id,
                owner_id,
            )
            or (product_id and product_id.is_kit)
        )
