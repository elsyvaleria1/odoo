from odoo import models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_fields_whatsapp_safe(self) -> set:
        return {
            "partner_id.name",
            "name",
            "company_id.name",
            "currency_id.symbol",
            "amount_total",
            "portal_url",
        }
