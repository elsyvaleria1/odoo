from odoo import models

from odoo.addons.whatsapp.tools import phone_validation as wa_phone_validation


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
        if verdict:
            delivery._answer(
                verdict,
                payload={
                    "whatsapp_message": message.get("id"),
                    "from": message.get("from"),
                },
                signer_request=False,
            )

    def _is_same_number(self, address, sender) -> bool:
        if not address or not sender:
            return False
        return wa_phone_validation.wa_phone_format_for_blacklist(
            address
        ) == wa_phone_validation.wa_phone_format_for_blacklist(sender)
