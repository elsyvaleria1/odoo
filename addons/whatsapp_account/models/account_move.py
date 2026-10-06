from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_fields_whatsapp_safe(self) -> set:
        return {
            "partner_id.name",
            "name",
            "company_id.name",
            "currency_id.symbol",
            "amount",
        }
