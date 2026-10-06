from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_product_config_update"):
            for product in self.with_privilege(
                "pos_urban_piper_enhancements.privilege_read_urban_piper_configs",
                reason="the configurations linked to a product, copied onto its values",
            ):
                product.attribute_line_ids.product_template_value_ids.urbanpiper_pos_config_ids = product.urbanpiper_pos_config_ids
        return res
