import logging

from odoo import models
from odoo.exceptions import AccessError

from odoo.addons.telegram.tools.dispatch import message_kind

_logger = logging.getLogger(__name__)


class TelegramHandlerAutomation(models.AbstractModel):
    """Answers to the questions workflow steps asked on Telegram.

    A message is taken only while a question is open in its chat and only
    when it can answer it: of a kind the question accepts, or a reply to the
    question itself. Anything else reaches the bot's other features exactly as
    if no question were open, so a question never blocks the chat the way a
    flow does. The answer is only recorded here; the dispatcher delivers it.
    """

    _name = "telegram.handler.automation"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Workflow Questions"

    def _feature_enabled(self, bot):
        # a question names its own chat, on whichever bot it was asked
        return True

    def _claims_message(self, bot, chat, message, partner, internal_user) -> bool:
        wait, refused = self._question_answered(chat, message)
        return bool(wait or refused)

    def _on_message(self, bot, chat, message, partner, internal_user):
        wait, refused = self._question_answered(chat, message)
        if wait:
            wait._record_answer(message, message_kind(message))
            bot._queue_reaction(chat, message["message_id"])
            return True
        if refused:
            tr = self._tr(bot, chat)
            labels = {
                "text": tr._("a text message"),
                "photo": tr._("a photo"),
                "document": tr._("a file"),
                "voice": tr._("a voice note"),
                "contact": tr._("a contact"),
                "location": tr._("a location"),
            }
            expected = ", ".join(
                labels.get(kind, kind) for kind in refused._get_accepted_kinds()
            )
            bot._queue_text(
                chat,
                tr._("To answer this, please send %(expected)s.", expected=expected),
                html=False,
                reply_to=message.get("message_id"),
            )
            return True
        return False

    def _question_answered(self, chat, message):
        if chat.chat_type != "private":
            waits = self.env["automation.telegram.wait"]
            return waits, waits
        waits = self.env["automation.telegram.wait"].with_privilege(
            "automation_telegram.privilege_answer_question",
            reason="a message in a chat answers the workflow question asked there",
        )
        # the router asks before any handler runs, outside the savepoint a
        # handler gets: a question whose run the sender may not see must leave
        # the message to the bot, not fail its delivery
        try:
            return waits._find_for_message(chat, message, message_kind(message))
        except AccessError as error:
            _logger.info(
                "Chat %s: a workflow question is out of the sender's reach: %s",
                chat.id,
                error,
            )
            return waits.browse(), waits.browse()
