from odoo import models


class PosOrderLine(models.Model):
    _inherit = "pos.order.line"

    def _get_pricing_exemptions(self):
        exemptions = super()._get_pricing_exemptions()
        discount_products = self.order_id.config_id.discount_product_id
        for line in self:
            if line.product_id in discount_products:
                exemptions[line] |= {"price_unit", "discount", "tax_ids"}
        return exemptions
