import logging

from markupsafe import escape

from odoo import models

_logger = logging.getLogger(__name__)

_CUSTOMER_FILES = ("photo", "document", "voice", "audio", "video")


class TelegramHandlerLivechat(models.AbstractModel):

    _name = "telegram.handler.livechat"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Live Chat"

    def _feature_enabled(self, bot):
        return bool(bot.livechat_channel_id)

    def _telegram_callback_prefixes(self):
        return ("lc:",)

    def _is_customer_chat(self, bot, chat, internal_user) -> bool:
        return (
            not internal_user
            and chat.chat_type == "private"
            and bool(chat.account_id)
            and bool(bot.livechat_channel_id)
        )

    def _claims_message(self, bot, chat, message, partner, internal_user) -> bool:
        return self._is_customer_chat(bot, chat, internal_user) and bool(
            self._serving(self.env["discuss.channel"]).search_count(
                [("telegram_chat_id", "=", chat.id), ("livechat_end_dt", "=", False)],
                limit=1,
            )
        )

    def _telegram_intakes(self):
        return frozenset({"text", "photo", "document", "voice"})

    def _accepts_idle(self, bot, chat, kind, message, partner, internal_user):
        return kind in self._telegram_intakes() and self._is_customer_chat(
            bot, chat, internal_user
        )

    def _telegram_intake_label(self, bot, chat, kind):
        return self._tr(bot, chat)._("Talk to us")

    @staticmethod
    def _serving(records):
        return records.with_privilege(
            "im_livechat_telegram.privilege_serve_customers",
            "mail.privilege_post_as_author",
            reason="a Telegram customer is answered in their live chat session",
        )


    def _customer(self, chat):
        return chat.account_id._contact()

    def _session(self, bot, chat, partner) -> tuple:
        sessions = self._serving(self.env["discuss.channel"])
        session = sessions.search(
            [("telegram_chat_id", "=", chat.id), ("livechat_end_dt", "=", False)],
            order="id desc",
            limit=1,
        )
        if session:
            return session, False, False
        previous = sessions.search(
            [("telegram_chat_id", "=", chat.id)], order="id desc", limit=1
        )
        lang = self.env["res.lang"].search([("code", "=", partner.lang)], limit=1)
        session = self._livechat_channel(bot)._open_session(
            visitor_partner=partner,
            country=partner.country_id,
            lang=lang,
            previous_operator=previous.livechat_operator_id,
            chatbot_script=bot.livechat_chatbot_script_id or None,
            allow_waiting=True,
            **self._session_options(bot, chat),
        )
        return (
            sessions.browse(session.ids),
            True,
            session.livechat_status == "need_help",
        )

    def _livechat_channel(self, bot):
        return (
            self.env["im_livechat.channel"]
            .with_privilege(
                "im_livechat.privilege_open_session",
                reason="a Telegram customer's message opens their live chat session",
            )
            .browse(bot.livechat_channel_id.id)
        )

    def _session_options(self, bot, chat):
        return {"extra_vals": {"telegram_chat_id": chat.id}}

    def _on_message(self, bot, chat, message, partner, internal_user):
        customer = self._customer(chat)
        session, opened, waiting = self._session(bot, chat, customer)
        tr = self._tr(bot, chat)
        if not session:
            bot.send_message(
                chat.chat_id,
                tr._("Nobody can answer here right now. Please try again later."),
                parse_mode=None,
            )
            return True
        if waiting:
            waiting = bot.with_context(lang=customer.lang).livechat_waiting_message
            if waiting:
                bot._queue_text(chat, waiting, html=False)
        body = self._body_of(message)
        attachments = self._download(bot, message, kinds=_CUSTOMER_FILES)
        if not body and not attachments:
            bot.send_message(
                chat.chat_id,
                tr._("Only text, photos and documents reach us here."),
                parse_mode=None,
            )
            return True
        posted = session.with_context(telegram_inbound=True).message_post(
            author_id=customer.id,
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachments=attachments,
        )
        self._link_inbound(bot, chat, message, posted)
        self._customer_posted(bot, chat, session, posted, opened)
        return True

    def _customer_posted(self, bot, chat, session, posted, opened) -> None:
        if session.chatbot_current_step_id and not opened:
            session._chatbot_run()


    def _on_business_message(
        self, bot, connection, chat, message, from_owner, edited
    ) -> bool:
        if not bot.livechat_channel_id:
            return False
        if edited:
            self._edit_inbound(bot, chat, message)
            return True
        body = self._body_of(message)
        attachments = self._download(bot, message, kinds=_CUSTOMER_FILES)
        if not body and not attachments:
            return True
        owner = connection.user_id
        session = self._business_session(bot, chat, owner)
        if not session:
            return True
        author = owner.partner_id if from_owner else self._customer(chat)
        posted = session.with_context(telegram_inbound=True).message_post(
            author_id=author.id,
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
            attachments=attachments,
        )
        self._link_inbound(bot, chat, message, posted)
        return True

    def _business_session(self, bot, chat, owner):
        sessions = self._serving(self.env["discuss.channel"])
        session = sessions.search(
            [("telegram_chat_id", "=", chat.id), ("livechat_end_dt", "=", False)],
            order="id desc",
            limit=1,
        )
        if session:
            return session
        customer = self._customer(chat)
        lang = self.env["res.lang"].search([("code", "=", customer.lang)], limit=1)
        session = self._livechat_channel(bot)._open_session(
            visitor_partner=customer,
            country=customer.country_id,
            lang=lang,
            forced_agent=owner,
            extra_vals={"telegram_chat_id": chat.id},
        )
        return sessions.browse(session.ids)

    def _on_business_deleted(self, bot, connection, chat, ledgers) -> bool:
        for posted in ledgers.mail_message_id:
            session = self._serving(self.env["discuss.channel"]).browse(posted.res_id)
            if posted.model == "discuss.channel" and session.telegram_chat_id == chat:
                session.with_context(telegram_inbound=True)._message_update_content(
                    posted.with_env(session.env), body="", attachment_ids=[]
                )
        return True

    def _edit_inbound(self, bot, chat, message) -> None:
        ledger = self.env["telegram.message"].search(
            [
                ("bot_id", "=", bot.id),
                ("chat_id", "=", chat.id),
                ("msg_uid", "=", str(message.get("message_id"))),
                ("mail_message_id", "!=", False),
            ],
            limit=1,
        )
        posted = ledger.mail_message_id
        body = self._body_of(message)
        if posted.model != "discuss.channel" or not body:
            return
        session = self._serving(self.env["discuss.channel"]).browse(posted.res_id)
        session.with_context(telegram_inbound=True)._message_update_content(
            posted.with_env(session.env), body=body
        )


    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        _prefix, action, *args = data.split(":")
        bot.answer_callback_query(callback_query.get("id"))
        if action == "ans" and args:
            self._answer(bot, chat, int(args[0]))
        elif action == "rate" and len(args) == 2:
            self._rate(bot, chat, int(args[0]), int(args[1]))
        elif not self._on_session_button(bot, chat, action, args):
            return False
        self._clear_keyboard(bot, chat, callback_query)
        return True

    def _on_session_button(self, bot, chat, action, args):
        return False

    def _open_session_of(self, chat):
        return self._serving(self.env["discuss.channel"]).search(
            [("telegram_chat_id", "=", chat.id), ("livechat_end_dt", "=", False)],
            order="id desc",
            limit=1,
        )

    def _answer(self, bot, chat, answer_id):
        session = self._open_session_of(chat)
        step = session.chatbot_current_step_id
        answer = step.answer_ids.filtered(lambda a: a.id == answer_id)
        if not session or not answer:
            return
        asked = session.env["chatbot.message"].search(
            [("discuss_channel_id", "=", session.id), ("script_step_id", "=", step.id)],
            order="id desc",
            limit=1,
        )
        asked.user_script_answer_id = answer
        posted = session.with_context(telegram_inbound=True).message_post(
            author_id=self._customer(chat).id,
            body=escape(answer.name),
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        _logger.debug("Chatbot answer %s posted as %s", answer.id, posted.id)
        session._chatbot_run()

    def _rate(self, bot, chat, session_id, value) -> None:
        session = self._serving(self.env["discuss.channel"]).browse(session_id).exists()
        if not session or session.telegram_chat_id != chat:
            return
        session._livechat_rate(value, partner=self._customer(chat))
        bot.send_message(
            chat.chat_id, self._tr(bot, chat)._("Thank you!"), parse_mode=None
        )
