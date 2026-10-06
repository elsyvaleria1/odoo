from odoo import models


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    def _enable_rental_price(self, *args, **kwargs):
        return super()._enable_rental_price(*args, **kwargs) or self.env.context.get(
            "website_id"
        )
