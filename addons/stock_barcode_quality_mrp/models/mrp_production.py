from odoo import models


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def _get_fields_stock_barcode(self):
        fields = super()._get_fields_stock_barcode()
        fields.append("quality_check_todo")
        return fields
