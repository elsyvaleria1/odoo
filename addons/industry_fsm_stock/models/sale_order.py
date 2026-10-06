from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _requires_lines_to_confirm(self):
        """The FSM auto-confirm happens before any material is on the order.

        `_fsm_get_or_create_sale_order` / `_fsm_create_sale_order` in this module confirm the
        order as soon as the task needs one, deliberately and before the technician has
        added a single product. Confirmation is what binds the order -- and the pickings
        it generates -- to *that* user's warehouse. Waiting for the first product would
        mean every line already on the order, including any added during a pre-sale
        phase, gets picked from the technician's default warehouse instead of the one it
        was sold from.

        Keyed on the context those two call sites set, not on the order: what makes
        "empty" expected here is *this* confirmation, not the record. An FSM order
        confirmed by hand, or from anywhere else, still has to carry a line. The key is
        the module's existing one, already meaning "this is the FSM auto-confirm" where
        `_is_lock_required` reads it.
        """
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
