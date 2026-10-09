from odoo import models

from ..services.insight_assistant import InsightAssistant
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.dispatch import translation_env

GROUP = "insight_telegram.group_insight_telegram"
AUTHORIZE = "ins_ok"
CANCEL = "ins_no"
DETAIL = "ins_det:"
PDF = "ins_pdf:"
CALLBACKS = (AUTHORIZE, CANCEL, DETAIL, PDF)


class TelegramHandlerInsight(models.AbstractModel):
    _name = "telegram.handler.insight"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Ask Odoo"

    # no command: on a bot that answers questions, whatever a member writes or
    # says is a question
    def _telegram_intakes(self):
        return frozenset({"text", "voice", "photo", "document", "audio", "video"})

    def _telegram_callback_prefixes(self):
        return CALLBACKS

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        if not data.startswith(CALLBACKS):
            return False
        bot.answer_callback_query(callback_query.get("id"))
        if not data.startswith((DETAIL, PDF)):
            # authorizing or cancelling answers once; a statement keeps its buttons
            self._clear_keyboard(bot, chat, callback_query)
        if not self._may_ask(bot, internal_user):
            return True
        if data.startswith((DETAIL, PDF)):
            # a statement's button: its breakdown or its PDF, for that partner
            action = "statement_detail" if data.startswith(DETAIL) else "statement_pdf"
            chat.delayed(
                identity_key=f"telegram_insight:{chat.id}:cb:{callback_query.get('id')}"
            )._insight_answer(
                bot.id,
                {
                    "insight_action": action,
                    "partner_id": int(data.split(":", 1)[1] or 0),
                },
                bot._acting_company().id,
            )
            return True
        # a button stands for the words: the job decides as it would for them
        words = "autorizo" if data == AUTHORIZE else "cancelar"
        chat.delayed(
            identity_key=f"telegram_insight:{chat.id}:cb:{callback_query.get('id')}"
        )._insight_answer(bot.id, {"text": words}, bot._acting_company().id)
        return True

    def _telegram_intake_label(self, bot, chat, kind):
        return self._tr(bot, chat)._("Question about Odoo")

    def _accepts_idle(self, bot, chat, kind, message, partner, internal_user):
        return bool(
            kind in self._telegram_intakes()
            and not chat._flow_is_open()
            and self._may_ask(bot, internal_user)
        )

    @staticmethod
    def _may_ask(bot, internal_user) -> bool:
        """Whether `internal_user` gets answers from `bot`: the bot's setting
        and their membership, read on the bot's behalf."""
        group = bot.env.ref(GROUP, raise_if_not_found=False)
        return bool(
            bot.insight_ai_enabled
            and internal_user
            and group
            and group in internal_user.all_group_ids
        )

    def _on_message(self, bot, chat, message, partner, internal_user):
        if chat._flow_is_open() or not self._may_ask(bot, internal_user):
            return False
        self._ask(bot, chat, message)
        return True

    def _ask(self, bot, chat, message) -> None:
        """Queue the answer: the model takes longer than Telegram waits for a
        webhook, so it runs as a job that replies when done."""
        bot.send_chat_action(chat, "typing")
        message_id = message.get("message_id")
        # a webhook Telegram delivers twice queues one answer
        identity = f"telegram_insight:{chat.id}:{message_id}" if message_id else None
        chat.delayed(identity_key=identity)._insight_answer(
            bot.id, message, bot._acting_company().id
        )

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not self._may_ask(bot, internal_user):
            return []
        tr_env = translation_env(bot, chat)
        lines = [
            tr_env._(
                "Ask anything about the data in Odoo, in your own words: sales, "
                "collections, inventory, purchases, production, people."
            ),
            tr_env._("Example: %(example)s")
            % {"example": tg.code("¿Cuánto vendimos este mes por sucursal?")},
            tr_env._(
                "You can also send photos and files, ask for any document as a "
                "PDF, or ask it to create or change something: it asks you to "
                "say «autorizo» before doing it, and it never deletes. It "
                "remembers the last few questions, so you can follow up."
            ),
        ]
        if InsightAssistant(bot).supports_audio:
            lines.append(tr_env._("You can also ask with a voice note 🎙."))
        return [(tr_env._("Questions about Odoo"), lines)]
