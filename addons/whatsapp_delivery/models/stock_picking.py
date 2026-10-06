from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _get_fields_whatsapp_safe(self) -> set:
        return {"partner_id.name", "name", "company_id.name", "carrier_tracking_url"}
