from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def _get_fields_whatsapp_safe(self) -> set:
        return {"partner_id.phone_ids", "currency_id.symbol"}
