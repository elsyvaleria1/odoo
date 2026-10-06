from odoo import api, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.model
    def _get_fields_stock_barcode(self):
        return super()._get_fields_stock_barcode() + ["is_kit"]
