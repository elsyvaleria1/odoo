from odoo import models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def write(self, vals):
        if "list_price" in vals:
            for record in self:
                for product in record.product_variant_ids:
                    product.pricer_product_to_create_or_update = True

        return super().write(vals)
