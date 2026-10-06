from odoo import api, models


class StockPackageType(models.Model):
    _inherit = "stock.package.type"
    _barcode_field = "barcode"

    @api.model
    def _get_fields_stock_barcode(self):
        return ["barcode", "name"]
