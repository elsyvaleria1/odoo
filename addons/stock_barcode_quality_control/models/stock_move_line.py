from odoo import models


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _get_fields_stock_barcode(self):
        fields = super()._get_fields_stock_barcode()
        fields.append("check_state")
        return fields

    def _is_checkable_from_context(self) -> bool:
        if self.env.context.get("barcode_trigger"):
            if not self.picked:
                return False
        return super()._is_checkable_from_context()
