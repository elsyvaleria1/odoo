from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _requires_lines_to_confirm(self):
        self.check_singleton()
        if self.env.context.get("fsm_create_sale_order"):
            return False
        return super()._requires_lines_to_confirm()

    def _is_lock_required(self) -> bool:
        self.check_singleton()
        if self.env.context.get("fsm_create_sale_order"):
            return False
        return super()._is_lock_required()

    def _get_product_catalog_order_data(self, products, **kwargs):
        product_catalog = super()._get_product_catalog_order_data(products, **kwargs)
        if not self.env.context.get("fsm_task_id"):
            return product_catalog
        for product in products:
            if product.id in product_catalog:
                product_catalog[product.id]["tracking"] = product.tracking not in [
                    "none",
                    False,
                ]
        return product_catalog
