from odoo import Command, api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def _update_product_by_barcodelookup(self, product, barcode_lookup_data):
        product.check_singleton()
        description = super()._update_product_by_barcodelookup(
            product, barcode_lookup_data
        )
        if not product.description_ecommerce:
            _debug.lifecycle("ecommerce_description_seeded", product=product)
            product.description_ecommerce = description
        return description

    def _set_lookup_image(self, product, img):
        image = super()._set_lookup_image(product, img)
        if image is not True:
            self.product_template_image_ids = [
                Command.create(
                    {
                        "name": product.name,
                        "image_1920": image,
                    }
                )
            ]
        return image
