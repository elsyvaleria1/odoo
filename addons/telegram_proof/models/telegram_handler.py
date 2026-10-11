from typing import Any

from odoo import fields, models
from odoo.exceptions import UserError

from .proof_method import ANSWERS, CALLBACK

COMMENT_MAX_LENGTH = 2000


class TelegramHandlerProof(models.AbstractModel):
    _name = "telegram.handler.proof"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Confirmations"

    def _telegram_callback_prefixes(self):
        return (CALLBACK,)

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("telling us what is not right")

    def _on_account_bound(self, bot, chat, binding) -> None:
        if binding.method == "contact":
            return
        partners = binding.partner_id | binding.partner_id.commercial_partner_id
        self.env["proof.challenge"]._with_proof_privilege().search(
            [
                ("kind", "=", "confirm"),
                ("state", "=", "issued"),
                ("partner_id", "in", partners.ids),
            ]
        )._reach_again()

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        tr = self._tr(bot, chat)
        delivery_id, _sep, answer = (
            (callback_query.get("data") or "").removeprefix(CALLBACK).partition(":")
        )
        delivery = self._get_delivery(delivery_id)
        message_id = (callback_query.get("message") or {}).get("message_id")
        if (
            answer not in ANSWERS
            or not delivery
            or delivery.method_id.code != "telegram_confirm"
            or delivery.address != str(chat.id)
            or delivery.method_id._get_delivery_ledger(delivery).msg_uid
            != str(message_id)
            or not self._binding_speaks_for(chat.account_id.binding_id, delivery)
        ):
            bot.send_message(chat.chat_id, tr._("That button is no longer valid."))
            return True
        self._clear_keyboard(bot, chat, callback_query)
        try:
            evidence = delivery._answer(
                ANSWERS[answer],
                payload=self._get_answer_payload(chat, callback_query),
                signer_request=False,
            )
        except UserError:
            bot.send_message(
                chat.chat_id,
                tr._("This request was already answered or is no longer current."),
            )
            return True
        if ANSWERS[answer] == "confirmed":
            bot.send_message(chat.chat_id, tr._("Thank you. You confirmed it."))
            return True
        if chat._flow_is_open():
            bot.send_message(chat.chat_id, tr._("Thank you. We will contact you."))
            return True
        self._flow_start(chat, "comment", {"evidence": evidence.id})
        bot.send_message(
            chat.chat_id,
            tr._(
                "Thank you. We will contact you. If you want, write here what is "
                "not right."
            ),
        )
        return True

    @staticmethod
    def _binding_speaks_for(binding, delivery) -> bool:
        partner = binding.partner_id
        return bool(
            binding.state == "active"
            and binding.method != "contact"
            and partner
            and partner.commercial_partner_id
            == delivery.partner_id.commercial_partner_id
        )

    def _on_message(self, bot, chat, message, partner, internal_user):
        if self._flow_step(chat) != "comment":
            return False
        tr = self._tr(bot, chat)
        text = (message.get("text") or "").strip()[:COMMENT_MAX_LENGTH]
        if not text:
            bot.send_message(chat.chat_id, tr._("Write it as a text message, please."))
            return True
        evidence_id = self._flow_data(chat).get("evidence")
        self._flow_end(chat)
        challenge = (
            self.env["proof.challenge"]
            ._with_proof_privilege()
            .search([("evidence_id", "=", evidence_id)], limit=1)
        )
        if challenge:
            challenge._notify_record(
                "_on_confirmation_comment", challenge.evidence_id, text
            )
        bot.send_message(chat.chat_id, tr._("Thank you. We passed it on."))
        return True

    def _get_delivery(self, delivery_id: str) -> models.BaseModel:
        deliveries = (
            self.env["proof.challenge"]._with_proof_privilege().env["proof.delivery"]
        )
        if not delivery_id.isdecimal():
            return deliveries
        return deliveries.browse(int(delivery_id)).exists()

    def _get_answer_payload(self, chat, callback_query) -> dict[str, Any]:
        binding = chat.account_id.binding_id
        return {
            "chat": chat.id,
            "message": (callback_query.get("message") or {}).get("message_id"),
            "telegram_user": (callback_query.get("from") or {}).get("id"),
            "binding": binding.id,
            "binding_partner": binding.partner_id.id,
            "binding_method": binding.method,
            "bound_at": fields.Datetime.to_string(binding.proven_at),
            "invited_by": binding.invited_by_id.id or None,
        }
