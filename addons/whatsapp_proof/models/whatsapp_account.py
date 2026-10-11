import logging

from odoo import models
from odoo.exceptions import UserError

from odoo.addons.whatsapp.tools import phone_validation as wa_phone_validation

_logger = logging.getLogger(__name__)
_MOBILE_PREFIX = {"52": "1", "54": "9"}


class WhatsappAccount(models.Model):
    _inherit = "whatsapp.account"

    def _on_button_reply(self, parent_whatsapp_message, message) -> None:
        super()._on_button_reply(parent_whatsapp_message, message)
        if not parent_whatsapp_message:
            return
        deliveries = (
            self.env["proof.challenge"]._with_proof_privilege().env["proof.delivery"]
        )
        delivery = deliveries.search(
            [
                ("ref", "=", str(parent_whatsapp_message.id)),
                ("method_id.code", "=", "whatsapp_confirm"),
                ("state", "=", "sent"),
            ],
            limit=1,
        )
        if not delivery or not self._is_same_number(
            delivery.address, message.get("from")
        ):
            return
        verdict = delivery.method_id._get_reply_verdict(
            parent_whatsapp_message, message
        )
        if not verdict:
            return
        try:
            with self.env.cr.savepoint():
                delivery._answer(
                    verdict,
                    payload={
                        "whatsapp_message": message.get("id"),
                        "from": message.get("from"),
                    },
                    signer_request=False,
                )
        except UserError as refusal:
            _logger.info("WhatsApp confirmation %s not taken: %s", delivery.id, refusal)

    def _is_same_number(self, address, sender) -> bool:
        if not address or not sender:
            return False
        return self._canonical_number(address) == self._canonical_number(sender)

    def _canonical_number(self, number) -> str:
        digits = "".join(
            char
            for char in wa_phone_validation.wa_phone_format_for_blacklist(number)
            if char.isdigit()
        )
        for country, extra in _MOBILE_PREFIX.items():
            if digits.startswith(country + extra) and len(digits) == len(country) + 11:
                return country + digits[len(country) + 1 :]
        return digits
