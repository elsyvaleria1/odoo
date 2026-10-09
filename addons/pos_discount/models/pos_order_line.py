from odoo import api, models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    @api.depends(
        "order_id",
        "order_id.fiscal_position_id",
        "tax_ids",
        "product_id",
        "order_id.config_id.discount_product_id",
    )
    def _compute_tax_ids_after_fiscal_position(self) -> None:
        super()._compute_tax_ids_after_fiscal_position()
        # the till builds a global discount from taxes the fiscal position
        # already mapped, and does not map them again
        for line in self._filter_global_discounts():
            line.tax_ids_after_fiscal_position = line.tax_ids

    def _filter_global_discounts(self):
        return self.filtered(
            lambda line: (
                line.product_id
                and line.product_id == line.order_id.config_id.discount_product_id
            )
        )

    def _get_pricing_exemptions(self):
        exemptions = super()._get_pricing_exemptions()
        for line in self._filter_global_discounts():
            exemptions[line] |= {"price_unit", "discount", "tax_ids"}
        return exemptions
