from odoo import fields, models

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools.authority import operating

RATINGS = ((1, "😞"), (3, "😐"), (5, "😊"))


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    telegram_chat_id = fields.Many2one(
        comodel_name="telegram.chat",
        index="btree_not_null",
        readonly=True,
        ondelete="set null",
        help="The Telegram chat of the customer this live chat session serves.",
    )

    def _telegram_notification_kind(self, recipient):
        # an operator of a session gets it as a chat of theirs
        if self.channel_type == "livechat":
            # the owner of a business account read it on their own phone
            owner = operating(self.telegram_chat_id).business_connection_id.user_id
            if owner and recipient.get("id") == owner.partner_id.id:
                return None
            if recipient.get("notif") in ("inbox", "web_push"):
                return "chats"
            return None
        return super()._telegram_notification_kind(recipient)

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        recipients_data = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
        if self.channel_type == "livechat" and self.telegram_chat_id:
            self._telegram_mirror(message)
        return recipients_data

    def _telegram_mirror(self, message) -> None:
        """Send what operators and the chatbot post to the customer's chat;
        what the customer wrote came from there and goes nowhere."""
        if message.message_type != "comment" or self.env.context.get(
            "telegram_inbound"
        ):
            return
        session = self._telegram_serving()
        if message.author_id in session.livechat_customer_partner_ids:
            return
        chat = operating(self.telegram_chat_id)
        bot = chat.bot_id
        body = tg.from_odoo_html(message.body, self.get_base_url())
        chatbot = session.chatbot_current_step_id.chatbot_script_id
        is_bot = chatbot and message.author_id == chatbot.operator_partner_id
        # a business chat's answers already go out as its owner
        owner = chat.business_connection_id.user_id.partner_id
        if (
            bot.livechat_operator_label
            and not is_bot
            and message.author_id
            and message.author_id != owner
        ):
            author = message.author_id.user_livechat_username or message.author_id.name
            body = f"{tg.bold(author)}: {body}"
        keyboard = session._telegram_keyboard(message, is_bot)
        if body:
            bot._queue_text(
                chat, body, reply_markup=keyboard, mail_message_id=message.id
            )
        for attachment in message.attachment_ids:
            if attachment.type != "url":
                bot._queue_file(chat, attachment, mail_message_id=message.id)

    def _telegram_keyboard(self, message, is_bot):
        """The buttons a mirrored message carries: a chatbot question's
        answers."""
        step = self.chatbot_current_step_id
        # the chatbot posts a step while that step is the session's current
        # one, welcome steps included
        if is_bot and step.step_type == "question_selection":
            return {
                "inline_keyboard": [
                    [{"text": answer.name[:60], "callback_data": f"lc:ans:{answer.id}"}]
                    for answer in step.answer_ids
                ]
            }
        return None

    def _telegram_serving(self):
        return self.with_privilege(
            "im_livechat_telegram.privilege_serve_customers",
            reason="a live chat session's answer reaches its Telegram customer",
        )

    def _close_livechat_session(self, **kwargs):
        was_open = not self.livechat_end_dt
        result = super()._close_livechat_session(**kwargs)
        # a business account's customers are not asked by its owner to rate them
        chat = operating(self.telegram_chat_id)
        if was_open and chat and not chat.business_connection_id and self.message_ids:
            self._telegram_ask_rating()
        return result

    def _telegram_ask_rating(self) -> None:
        chat = operating(self.telegram_chat_id)
        session = self._telegram_serving()
        lang = session.livechat_customer_partner_ids[:1].lang or chat.bot_id.get_lang(
            chat
        )
        env = self.with_context(lang=lang).env
        chat.bot_id._queue_text(
            chat,
            env._("How did we do?"),
            reply_markup={
                "inline_keyboard": [
                    [
                        {"text": face, "callback_data": f"lc:rate:{self.id}:{value}"}
                        for value, face in RATINGS
                    ]
                ]
            },
        )
