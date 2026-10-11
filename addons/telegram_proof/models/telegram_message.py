from odoo import models

from .proof_method import CALLBACK


class TelegramMessage(models.Model):
    _inherit = "telegram.message"

    def _still_wanted(self) -> bool:
        delivery = self._get_proof_delivery()
        if delivery and delivery.state != "sent":
            return False
        return super()._still_wanted()

    def _on_delivery_failed(self, error, started) -> None:
        super()._on_delivery_failed(error, started)
        delivery = self._get_proof_delivery()
        if delivery.state == "sent":
            delivery.state = "failed"

    def _get_proof_delivery(self):
        self.check_singleton()
        deliveries = (
            self.env["proof.challenge"]._with_proof_privilege().env["proof.delivery"]
        )
        if CALLBACK not in str((self.payload or {}).get("reply_markup") or ""):
            return deliveries
        return deliveries.search(
            [("ref", "=", str(self.id)), ("method_id.code", "=", "telegram_confirm")],
            limit=1,
        )
