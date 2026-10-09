from itertools import starmap

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.authority import keeping, operating
from odoo.addons.telegram.tools.dispatch import translation_env

CALLBACK = "prf:"
ANSWERS = {"c": "confirmed", "d": "disputed"}


class ProofMethod(models.Model):
    _inherit = "proof.method"

    code = fields.Selection(
        selection_add=[
            ("telegram_code", "Telegram Code"),
            ("telegram_confirm", "Telegram Confirmation"),
        ],
        ondelete={"telegram_code": "cascade", "telegram_confirm": "cascade"},
    )

    def _is_enrolled(self, user: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code == "telegram_code":
            return bool(self._get_user_chat(user))
        return super()._is_enrolled(user)

    def _is_enrolled_contact(self, partner: models.BaseModel) -> bool:
        self.check_singleton()
        if self.code in ("telegram_code", "telegram_confirm"):
            return bool(self._get_contact_chat(partner))
        return super()._is_enrolled_contact(partner)

    def _uses_code(self) -> bool:
        self.check_singleton()
        return self.code == "telegram_code" or super()._uses_code()

    def _get_contact_chat(
        self, partner: models.BaseModel, company: models.BaseModel | None = None
    ) -> models.BaseModel:
        """The private chat that reaches ``partner``, preferring a bot of
        ``company``: only an account bound to the contact reaches them."""
        # the contact's own chats and their company's people's, never one a
        # stand-in contact holds: a stranger's first message made it
        chats = (
            operating(self.env["telegram.chat"])
            ._for_partner(partner | partner.child_ids)
            .filtered(
                lambda chat: (
                    not chat.bot_blocked
                    and chat.account_id.binding_id.method != "contact"
                )
            )
        )
        if company:
            chats = chats.sorted(
                lambda chat: company not in keeping(chat.bot_id).company_ids
            )
        return chats[:1]

    def _get_user_chat(self, user: models.BaseModel) -> models.BaseModel:
        return (
            operating(self.env["telegram.chat"])
            ._for_user(user)
            .filtered(lambda chat: not chat.bot_blocked)[:1]
        )

    def _get_signer_chat(
        self, challenge: models.BaseModel, signer: models.BaseModel
    ) -> models.BaseModel:
        if challenge.partner_id:
            return self._get_contact_chat(
                signer, challenge.company_id or challenge.user_id.company_id
            )
        return self._get_user_chat(challenge.user_id)

    def _send_code(
        self, challenge: models.BaseModel, signer: models.BaseModel, code: str
    ) -> str:
        self.check_singleton()
        if self.code != "telegram_code":
            return super()._send_code(challenge, signer, code)
        chat = self._get_signer_chat(challenge, signer)
        env = translation_env(chat.bot_id, chat) if chat else self.env
        text = "\n".join(
            [
                env._(
                    "%(asker)s asks you to confirm the following:",
                    asker=tg.bold(challenge.user_id.name),
                ),
                *self._get_summary_lines(challenge),
                "",
                env._(
                    "If you agree, give them this code: %(code)s", code=tg.bold(code)
                ),
                env._("If you did not expect this, do not give the code to anyone."),
            ]
        )
        if not chat or not chat.bot_id.send_message(chat.chat_id, text):
            raise UserError(
                self.env._(
                    "Telegram did not take the code for %(signer)s. Ask for "
                    "another way.",
                    signer=signer.display_name,
                )
            )
        return self._mask_chat(chat)

    def _deliver_confirmation(
        self, challenge: models.BaseModel, reminder: bool = False
    ) -> models.BaseModel:
        self.check_singleton()
        if self.code != "telegram_confirm":
            return super()._deliver_confirmation(challenge, reminder=reminder)
        chat = self._get_signer_chat(challenge, challenge.partner_id)
        if not chat:
            return self.env["proof.delivery"]
        delivery = self.env["proof.delivery"].create(
            {
                "challenge_id": challenge.id,
                "method_id": self.id,
                "sent_to": self._mask_chat(chat),
                "address": str(chat.id),
            }
        )
        env = translation_env(chat.bot_id, chat)
        company = (challenge.company_id or challenge.user_id.company_id).name
        text = "\n".join(
            [
                env._(
                    "Reminder: %(company)s asks you to confirm the following:",
                    company=tg.bold(company),
                )
                if reminder
                else env._(
                    "%(company)s asks you to confirm the following:",
                    company=tg.bold(company),
                ),
                *self._get_summary_lines(challenge),
                *starmap(tg.link, challenge._get_record_links()),
                "",
                env._("Is this right?"),
            ]
        )
        # through the outbox: sent once the asking transaction commits, so a
        # collection rolled back never reaches its customer
        ledger = chat.bot_id._queue_text(
            chat,
            text,
            reply_markup=kb.confirm_cancel(
                env._("Confirm, this is right"),
                f"{CALLBACK}{delivery.id}:c",
                env._("Not right"),
                f"{CALLBACK}{delivery.id}:d",
            ),
        )
        delivery.ref = str(ledger.id)
        return delivery

    def _withdraw_delivery(self, delivery: models.BaseModel) -> None:
        self.check_singleton()
        if self.code != "telegram_confirm":
            super()._withdraw_delivery(delivery)
            return
        ledger = self._get_delivery_ledger(delivery)
        if ledger.msg_uid:
            ledger.bot_id.edit_message_reply_markup(
                ledger.chat_id.chat_id, int(ledger.msg_uid), reply_markup=None
            )

    def _get_delivery_ledger(self, delivery: models.BaseModel) -> models.BaseModel:
        """The outbox row that carried the message, whose Telegram id the
        contact's button press names once it went out."""
        ledger = operating(self.env["telegram.message"])
        if not (delivery.ref or "").isdigit():
            return ledger
        return ledger.browse(int(delivery.ref)).exists()

    def _get_summary_lines(self, challenge: models.BaseModel) -> list[str]:
        return [
            f"{tg.escape(label)}: {tg.bold(value)}"
            for label, value in challenge.summary or []
        ]

    def _mask_chat(self, chat: models.BaseModel) -> str:
        username = chat.account_id.username
        if username:
            return f"Telegram @{username[:1]}{'*' * max(len(username) - 1, 1)}"
        return "Telegram"
