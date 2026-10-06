from odoo import api, models


class ProductTrace(models.Model):
    _inherit = "product.trace"

    @api.model
    def _get_fields_stock_barcode(self):
        return super()._get_fields_stock_barcode() + ["expiration_date"]
