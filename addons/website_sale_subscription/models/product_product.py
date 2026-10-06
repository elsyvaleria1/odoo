from odoo import models


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _website_can_be_added(self, product=None):
        return self.product_tmpl_id._website_can_be_added(product or self)

    def _can_show_website_quick_add(self) -> bool:
        self.check_singleton()
        return super()._can_show_website_quick_add() and self._website_can_be_added(
            product=self
        )

    def _is_add_to_cart_allowed(self) -> bool:
        self.check_singleton()
        return bool(
            super()._is_add_to_cart_allowed()
            and self._website_can_be_added(product=self)
        )
