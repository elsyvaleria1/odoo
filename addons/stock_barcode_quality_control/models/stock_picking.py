from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_fields_stock_barcode(self):
        fields = super()._get_fields_stock_barcode()
        fields.append("quality_check_todo")
        return fields
