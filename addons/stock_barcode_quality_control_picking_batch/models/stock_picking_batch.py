from odoo import api, models


class StockPickingBatch(models.Model):
    _inherit = "stock.picking.batch"

    @api.model
    def _get_fields_stock_barcode(self):
        fields = super()._get_fields_stock_barcode()
        fields.append("quality_check_todo")
        return fields
