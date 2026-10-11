from odoo import models
from odoo.tools.translate import LazyTranslate

from ..services.insight_assistant import InsightAssistant
from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.dispatch import (
    TelegramCommand,
    log_command_execution,
    translation_env,
)

_lt = LazyTranslate(__name__)

GROUP = "insight_telegram.group_insight_telegram"
HANDLER = "telegram.handler.insight"
AUTHORIZE = "ins_ok"
CANCEL = "ins_no"
DETAIL = "ins_det:"
PDF = "ins_pdf:"
COMPANY = "ins_co:"
CALLBACKS = (AUTHORIZE, CANCEL, DETAIL, PDF, COMPANY)
AUTHORIZE_ACTION = "authorize"
CANCEL_ACTION = "cancel"
PICK_COMPANY = "pick_company"
STATEMENT_DETAIL = "statement_detail"
STATEMENT_PDF = "statement_pdf"
CLEAR = "/clear"


def callback(prefix, *parts) -> str:
    head = prefix.rstrip(":")
    return ":".join([head, *(str(part) for part in parts if part not in (None, ""))])


def callback_parts(data, prefix) -> list:
    rest = data[len(prefix.rstrip(":")) :].lstrip(":")
    return rest.split(":") if rest else []


class TelegramHandlerInsight(models.AbstractModel):
    _name = HANDLER
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Ask Odoo"

    def _telegram_commands(self) -> dict:
        return {
            CLEAR: TelegramCommand(
                "_handle_clear_command",
                "internal",
                builtin=True,
                description=_lt("Forget this conversation and start over"),
            ),
        }

    def _feature_enabled(self, bot):
        return bool(bot.insight_ai_enabled)

    def _command_allowed(self, bot, chat, command, partner, internal_user) -> bool:
        if command == CLEAR and not self._may_ask(bot, internal_user):
            return False
        return super()._command_allowed(bot, chat, command, partner, internal_user)

    @log_command_execution
    def _handle_clear_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr_env = translation_env(bot, chat)
        chat._insight_forget()
        bot.send_message(
            chat.chat_id,
            tr_env._("Done, I forgot our conversation: we start from zero."),
            parse_mode=None,
        )

    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("the changes waiting for your authorization")

    def _telegram_intakes(self):
        return frozenset({"text", "voice", "photo", "document"})

    def _telegram_callback_prefixes(self):
        return CALLBACKS

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        bot.answer_callback_query(callback_query.get("id"))
        if not data.startswith((DETAIL, PDF)):
            self._clear_keyboard(bot, chat, callback_query)
        if not self._may_ask(bot, internal_user):
            return True
        if data.startswith((DETAIL, PDF)):
            parts = callback_parts(data, DETAIL if data.startswith(DETAIL) else PDF)
            message = {
                "insight_action": STATEMENT_DETAIL
                if data.startswith(DETAIL)
                else STATEMENT_PDF,
                "partner_id": int(parts[0]) if parts and parts[0].isdecimal() else 0,
            }
        elif data.startswith(COMPANY):
            parts = callback_parts(data, COMPANY)
            message = {
                "insight_action": PICK_COMPANY,
                "company_id": int(parts[0]) if parts and parts[0].isdecimal() else 0,
                "nonce": parts[1] if len(parts) > 1 else "",
            }
        else:
            prefix = AUTHORIZE if data.startswith(AUTHORIZE) else CANCEL
            parts = callback_parts(data, prefix)
            message = {
                "insight_action": AUTHORIZE_ACTION
                if prefix == AUTHORIZE
                else CANCEL_ACTION,
                "nonce": parts[0] if parts else "",
            }
        self._queue(bot, chat, message, f"cb:{callback_query.get('id')}")
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
        group = bot.env.ref(GROUP, raise_if_not_found=False)
        return bool(
            bot.insight_ai_enabled
            and internal_user
            and group
            and group in internal_user.all_group_ids
        )

    def _on_message(self, bot, chat, message, partner, internal_user):
        if chat._flow_is_open() and chat.flow_owner != self._name:
            return False
        if not self._may_ask(bot, internal_user):
            return False
        self._ask(bot, chat, message)
        return True

    def _ask(self, bot, chat, message) -> None:
        bot.send_chat_action(chat, "typing")
        message_id = message.get("message_id")
        self._queue(bot, chat, message, message_id)

    @staticmethod
    def _queue(bot, chat, message, key) -> None:
        identity = f"telegram_insight:{chat.id}:{key}" if key else None
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
            % {
                "example": tg.code(
                    tr_env._("How much did we sell this month by branch?")
                )
            },
            tr_env._(
                "You can also send photos and files, ask for any document as a "
                "PDF, or ask it to create or change something: it asks you to "
                "say «autorizo» before doing it, and it never deletes. It "
                "remembers the last few questions, so you can follow up."
            ),
            tr_env._("%(command)s - Forget this conversation and start over.")
            % {"command": CLEAR},
        ]
        if InsightAssistant(bot).supports_audio:
            lines.append(tr_env._("You can also ask with a voice note 🎙."))
        return [(tr_env._("Questions about Odoo"), lines)]
