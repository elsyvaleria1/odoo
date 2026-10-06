from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_fields_stock_barcode(self):
        """Inject the field 'quality_check_todo' in the initial state of the barcode view."""
        fields = super()._get_fields_stock_barcode()
        fields.append("quality_check_todo")
        return fields
