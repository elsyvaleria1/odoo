from odoo import api, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _get_fields_stock_barcode(self):
        return ["display_name"]
