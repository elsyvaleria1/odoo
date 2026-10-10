from odoo import models


class ProductComboItem(models.Model):
    _inherit = "product.combo.item"

    def _is_configurable(self) -> bool:
        self.check_singleton()
        product = self.product_id
        return any(
            ptal.attribute_id.create_variant == "no_variant" and ptal._is_configurable()
            for ptal in product.attribute_line_ids
        ) or any(
            ptav.is_custom for ptav in product.product_template_attribute_value_ids
        )

    def _is_preselected(self) -> bool:
        self.check_singleton()
        return len(self.combo_id.combo_item_ids) == 1 and not self._is_configurable()
