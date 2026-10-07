import logging
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.telegram.tools import format as tg
from odoo.addons.telegram.tools import keyboard as kb
from odoo.addons.telegram.tools.dispatch import (
    TelegramCommand,
    log_command_execution,
    message_kind,
    translation_env,
)

_logger = logging.getLogger(__name__)

_DRAFT_KEY = "mail_draft"
_REPLY_KEY = "mail_reply"
_FOCUS_KEY = "mail_focus"
_PICK_KEY = "mail_pick_colleague"
_RECENT_THREADS = 5
_RECENT_CONVERSATIONS = 6
_COLLEAGUES_SHOWN = 8
# a conversation stays open this long after the last message written to it
_FOCUS_TTL = timedelta(hours=1)
# what an open conversation takes: a contact or a location is someone else's
_FOCUS_KINDS = frozenset({"text", "photo", "document", "voice"})


class TelegramHandlerMail(models.AbstractModel):
    """Replies from Telegram to the Odoo messages the bot delivered.

    A reply to a delivered message is posted on its record or conversation
    as the person's user, under that user's access rights. A reply to an
    internal note stays a note; a reply to a public message that would email
    external followers asks first. Text sent without replying offers the
    person's recent conversations to post it to.
    """

    _name = "telegram.handler.mail"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Odoo Notifications and Replies"
    _telegram_intake_priority = 150

    def _telegram_callback_prefixes(self):
        return ("mt:",)

    def _telegram_intakes(self):
        return frozenset({"text"})

    def _feature_enabled(self, bot):
        return bot.notify_mail

    def _telegram_commands(self) -> dict:
        return {
            "/bandeja": TelegramCommand(
                "_handle_inbox_command", "internal", builtin=True
            ),
            "/escribir": TelegramCommand(
                "_handle_write_command", "internal", builtin=True
            ),
        }

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        if not bot.notify_mail or not internal_user:
            return []
        tr = translation_env(bot, chat)
        return [
            (
                tr._("Odoo Notifications"),
                [
                    tr._("/bandeja - Open your Odoo notifications and chats here."),
                    tr._(
                        "/escribir - Write to a colleague or a conversation of "
                        "Odoo, as in a chat."
                    ),
                ],
            )
        ]

    # -- the inbox Mini App ---------------------------------------------------

    @log_command_execution
    def _handle_inbox_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        """The inbox, as a button now and as the chat's menu button from now
        on."""
        refusal = self._get_chat_mail_refusal(bot, chat, internal_user)
        if refusal:
            self._explain_mail_refusal(bot, chat, internal_user, refusal)
            return
        tr = translation_env(bot, chat)
        url = bot._mini_app_url(f"/telegram/inbox/{bot.id}")
        if not url:
            bot._queue_text(
                chat,
                tr._(
                    "The inbox opens inside Telegram only while Odoo is served "
                    "over https. Ask your administrator."
                ),
                html=False,
            )
            return
        inbox = kb.web_app_button(tr._("📥 Inbox"), url)
        bot._queue_text(
            chat,
            tr._("Your Odoo notifications and chats, inside Telegram:"),
            html=False,
            reply_markup=kb.keyboard([inbox]),
        )
        self.env["telegram.message"]._queue(
            bot,
            chat,
            "setChatMenuButton",
            {"menu_button": {"type": "web_app", **inbox}},
        )

    # -- replies --------------------------------------------------------------

    def _delivered(self, bot, chat, telegram_message_id):
        """The mail message a Telegram message of this chat carried."""
        if not telegram_message_id:
            return self.env["mail.message"]
        ledger = self.env["telegram.message"].search(
            [
                ("bot_id", "=", bot.id),
                ("chat_id", "=", chat.id),
                ("msg_uid", "=", str(telegram_message_id)),
                ("mail_message_id", "!=", False),
            ],
            limit=1,
        )
        return ledger.mail_message_id

    def _claims_message(self, bot, chat, message, partner, internal_user) -> bool:
        if not internal_user or chat.chat_type != "private":
            return False
        replied = (message.get("reply_to_message") or {}).get("message_id")
        if self._delivered(bot, chat, replied):
            return True
        kind = message_kind(message)
        if kind == "text" and chat._get_context(_PICK_KEY):
            return True
        return kind in _FOCUS_KINDS and self._get_focus(chat, internal_user) is not None

    def _get_chat_mail_refusal(self, bot, chat, user) -> str | None:
        """Why this chat's Telegram account may not carry `user`'s Odoo mail
        now, in the person's words; None when it may."""
        tr = self._tr(bot, chat)
        if not user or not chat.account_id:
            return tr._("Connect Telegram to Odoo first.")
        return bot.with_env(tr)._get_mail_refusal(chat.account_id, user)

    def _explain_mail_refusal(self, bot, chat, user, refusal) -> None:
        if user and bot._is_phone_needed_for_mail(chat.account_id, user):
            bot._queue_phone_request(chat, refusal)
            return
        bot._queue_text(chat, refusal, html=False)

    def _on_message(self, bot, chat, message, partner, internal_user):
        refusal = self._get_chat_mail_refusal(bot, chat, internal_user)
        if refusal:
            self._explain_mail_refusal(bot, chat, internal_user, refusal)
            return True
        replied = (message.get("reply_to_message") or {}).get("message_id")
        parent = self._delivered(bot, chat, replied)
        if parent:
            self._reply(bot, chat, message, parent, internal_user)
            return True
        if message_kind(message) == "text" and chat._get_context(_PICK_KEY):
            chat._set_context(_PICK_KEY, False)
            self._offer_colleagues(bot, chat, internal_user, message.get("text"))
            return True
        focus = self._get_focus(chat, internal_user)
        if focus is not None:
            postable = self._get_postable(bot, chat, message, internal_user)
            posted = postable and self._post_from_telegram(bot, chat, postable, focus)
            if posted:
                self._update_focus(chat, focus)
                bot._queue_reaction(chat, message["message_id"])
            return True
        return self._offer_threads(bot, chat, message, internal_user)

    def _reply(self, bot, chat, message, parent, user, visibility=None) -> None:
        tr = self._tr(bot, chat)
        message = self._get_postable(bot, chat, message, user)
        if message is None:
            return
        thread = self._thread_of(parent, user)
        if thread is None:
            bot.send_message(
                chat.chat_id,
                tr._("You can no longer write on that conversation in Odoo."),
                parse_mode=None,
            )
            return
        if visibility is None:
            visibility = self._visibility(thread, parent)
            if visibility == "ask":
                self._ask_visibility(bot, chat, message, parent, thread)
                return
        posted = self._post_from_telegram(
            bot,
            chat,
            message,
            thread,
            parent=parent,
            subtype="mail.mt_note" if visibility == "note" else "mail.mt_comment",
        )
        if posted:
            bot.send_message(
                chat.chat_id,
                tr._("✓ Posted on %(thread)s")
                % {"thread": tg.escape(thread.display_name)},
            )

    def _get_postable(self, bot, chat, message, user):
        """`message` as Odoo can take it -- a voice note as its transcript --
        or None when it holds nothing Odoo takes; the person is told why."""
        tr = self._tr(bot, chat)
        if not self._body_of(message) and message_kind(message) == "voice":
            heard = self._voice_text(bot, chat, message, user)
            if heard is None:
                bot.send_message(
                    chat.chat_id,
                    tr._("I cannot turn voice notes into text here: please type it."),
                    parse_mode=None,
                )
                return None
            # the transcript stands for the note from here on, a pending
            # visibility question included
            message = {**message, "text": f"🎤 {heard}"}
        if not self._body_of(message) and not self._files_of(message):
            bot.send_message(
                chat.chat_id,
                tr._("Only text, photos and documents can be posted to Odoo."),
                parse_mode=None,
            )
            return None
        return message

    def _post_from_telegram(
        self, bot, chat, message, thread, *, parent=None, subtype="mail.mt_comment"
    ):
        """Post a postable Telegram message on `thread`, which the posting
        user's environment carries: its text and its photos and documents.
        The posted message, or None when the user may not write there -- the
        person is told so."""
        try:
            with self.env.cr.savepoint():
                posted = thread.message_post(
                    body=self._body_of(message),
                    parent_id=parent.id if parent else False,
                    message_type="comment",
                    subtype_xmlid=subtype,
                    attachments=self._download(bot, message),
                )
        except AccessError:
            bot.send_message(
                chat.chat_id,
                self._tr(bot, chat)._(
                    "You may read that conversation in Odoo but not write on it."
                ),
                parse_mode=None,
            )
            return None
        self._link_inbound(bot, chat, message, posted)
        return posted

    def _thread_of(self, parent, user):
        """The record or conversation `parent` is on, as `user` may write it."""
        if not parent.model or not parent.res_id:
            return None
        thread = self.env[parent.model].with_user(user).browse(parent.res_id).exists()
        if not thread or not thread.has_access("read"):
            return None
        return thread

    @staticmethod
    def _visibility(thread, parent) -> str:
        """A conversation takes a message; on a record, a reply keeps its
        parent's visibility -- a note stays a note -- and asks before it
        reaches external followers."""
        if thread._name == "discuss.channel":
            return "comment"
        if not parent.subtype_id or parent.subtype_id.internal:
            return "note"
        followers = thread.message_follower_ids.partner_id
        return "ask" if followers.filtered("partner_share") else "comment"

    def _ask_visibility(self, bot, chat, message, parent, thread) -> None:
        tr = self._tr(bot, chat)
        external = len(thread.message_follower_ids.partner_id.filtered("partner_share"))
        chat._set_context(
            _REPLY_KEY,
            {
                "parent_id": parent.id,
                "message": {
                    key: message[key]
                    for key in ("message_id", "text", "caption", "photo", "document")
                    if key in message
                },
            },
        )
        bot.send_message(
            chat.chat_id,
            tr._(
                "%(thread)s has %(count)s external follower(s): post your reply as "
                "an internal note, or as a message they receive?"
            )
            % {"thread": thread.display_name, "count": external},
            parse_mode=None,
            reply_markup=kb.keyboard(
                [
                    kb.button(tr._("📝 Internal note"), "mt:vis:note"),
                    kb.button(tr._("✉️ Message to followers"), "mt:vis:comment"),
                ]
            ),
        )

    def _on_edited_message(
        self, bot, chat, message, ledger, partner, internal_user
    ) -> bool:
        """Editing a reply in Telegram edits what it posted in Odoo, as its
        author and within Odoo's own rule on who may edit a message."""
        posted = ledger.mail_message_id
        if (
            not posted
            or not internal_user
            or posted.author_id != internal_user.partner_id
            or self._get_chat_mail_refusal(bot, chat, internal_user)
        ):
            return False
        thread = self._thread_of(posted, internal_user)
        body = self._body_of(message)
        if thread is None or not body:
            return False
        try:
            with self.env.cr.savepoint():
                thread._message_update_content(
                    posted.with_user(internal_user), body=body
                )
        except (AccessError, UserError) as error:
            _logger.info(
                "Telegram edit of message %s not applied to Odoo message %s: %s",
                message.get("message_id"),
                posted.id,
                error,
            )
            return False
        return True

    def _on_reaction(self, bot, chat, ledger, account, *, added, removed) -> bool:
        """A reaction to a delivered notification is the user's reaction to
        the Odoo message, where they may read it."""
        posted = ledger.mail_message_id
        user = account._acting_user("internal")
        if chat.chat_type != "private" or not posted or not user:
            return False
        if self._get_chat_mail_refusal(bot, chat, user):
            return False
        thread = self._thread_of(posted, user)
        if thread is None:
            return False
        self._react(posted.with_env(thread.env), user.partner_id, added, removed)
        return True

    # -- text without a reply -------------------------------------------------

    def _accepts_idle(self, bot, chat, kind, message, partner, internal_user):
        return (
            kind == "text"
            and bool(internal_user)
            and chat.chat_type == "private"
            and bool(self._recent_threads(bot, chat))
            and not self._get_chat_mail_refusal(bot, chat, internal_user)
        )

    def _recent_threads(self, bot, chat):
        ledgers = self.env["telegram.message"].search(
            [
                ("bot_id", "=", bot.id),
                ("chat_id", "=", chat.id),
                ("mail_message_id", "!=", False),
                ("message_type", "=", "outbound"),
            ],
            order="id desc",
            limit=50,
        )
        seen, recent = set(), []
        for ledger in ledgers:
            key = (ledger.mail_message_id.model, ledger.mail_message_id.res_id)
            if key in seen or not all(key):
                continue
            seen.add(key)
            recent.append(ledger.mail_message_id)
            if len(recent) == _RECENT_THREADS:
                break
        return recent

    def _offer_threads(self, bot, chat, message, user) -> bool:
        tr = self._tr(bot, chat)
        recent = self._recent_threads(bot, chat)
        if not recent:
            return False
        chat._set_context(_DRAFT_KEY, {"text": message.get("text") or ""})
        bot.send_message(
            chat.chat_id,
            tr._("Where should I post it? Reply to a notification to skip this."),
            parse_mode=None,
            reply_markup=kb.record_list(
                recent,
                lambda parent: (self._thread_of(parent, user) or parent).display_name,
                lambda parent: f"mt:to:{parent.id}",
                width=60,
                trailing=[kb.button(tr._("Cancel"), "mt:to:0")],
            ),
        )
        return True

    # -- buttons --------------------------------------------------------------

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        tr = self._tr(bot, chat)
        if not internal_user:
            bot.answer_callback_query(
                callback_query.get("id"), tr._("Connect Telegram to Odoo first.")
            )
            return True
        refusal = self._get_chat_mail_refusal(bot, chat, internal_user)
        if refusal:
            # a button's answer holds 200 characters at most
            bot.answer_callback_query(callback_query.get("id"), refusal[:200])
            return True
        _prefix, action, argument = (data.split(":", 2) + ["", ""])[:3]
        if action == "read":
            self._mark_read(internal_user, int(argument or 0))
            bot.answer_callback_query(callback_query.get("id"), tr._("✓ Read"))
            return True
        if action == "vis":
            pending = chat._get_context(_REPLY_KEY) or {}
            chat._set_context(_REPLY_KEY, False)
            parent = self.env["mail.message"].browse(pending.get("parent_id") or 0)
            bot.answer_callback_query(callback_query.get("id"))
            self._clear_keyboard(bot, chat, callback_query)
            if parent.exists() and argument in ("note", "comment"):
                self._reply(
                    bot,
                    chat,
                    pending["message"],
                    parent,
                    internal_user,
                    visibility=argument,
                )
            return True
        if action == "to":
            draft = chat._get_context(_DRAFT_KEY) or {}
            chat._set_context(_DRAFT_KEY, False)
            bot.answer_callback_query(callback_query.get("id"))
            self._clear_keyboard(bot, chat, callback_query)
            parent = self.env["mail.message"].browse(int(argument or 0)).exists()
            if parent and draft.get("text"):
                self._reply(bot, chat, {"text": draft["text"]}, parent, internal_user)
            return True
        if action in ("cv", "dm", "new", "end"):
            bot.answer_callback_query(callback_query.get("id"))
            self._clear_keyboard(bot, chat, callback_query)
            self._on_conversation_button(bot, chat, action, argument, internal_user)
            return True
        return False

    def _mark_read(self, user, mail_message_id) -> None:
        message = self.env["mail.message"].browse(mail_message_id).exists()
        if not message:
            return
        if message.model == "discuss.channel":
            member = self.env["discuss.channel.member"].search(
                [
                    ("channel_id", "=", message.res_id),
                    ("partner_id", "=", user.partner_id.id),
                ],
                limit=1,
            )
            if member:
                member._mark_as_read(message.id)
            return
        message.with_user(user).set_message_done()

    # -- conversations ----------------------------------------------------------

    @log_command_execution
    def _handle_write_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        """Choose where what is written here goes, as in a chat: a recent
        conversation, or a colleague -- `/escribir ana` looks one up at once."""
        refusal = self._get_chat_mail_refusal(bot, chat, internal_user)
        if refusal:
            self._explain_mail_refusal(bot, chat, internal_user, refusal)
            return
        # another feature's flow takes this chat's messages: it ends first
        owner = self._router()._flow_owner(chat)
        if owner is not None:
            self._router()._send_flow_busy_notice(bot, chat, owner, "/escribir")
            return
        if args:
            self._offer_colleagues(bot, chat, internal_user, " ".join(args))
            return
        tr = self._tr(bot, chat)
        trailing = [kb.button(tr._("➕ New conversation"), "mt:new")]
        if self._get_focus(chat, internal_user) is not None:
            trailing.append(kb.button(tr._("⏹ End"), "mt:end"))
        bot.send_message(
            chat.chat_id,
            tr._("Where do you want to write?"),
            parse_mode=None,
            reply_markup=kb.record_list(
                self._get_recent_conversations(internal_user),
                lambda channel: self._get_conversation_name(channel, internal_user),
                lambda channel: f"mt:cv:{channel.id}",
                width=60,
                trailing=trailing,
            ),
        )

    def _get_recent_conversations(self, user):
        """The Discuss conversations `user` is in, the liveliest first."""
        return (
            self.env["discuss.channel"]
            .with_user(user)
            .search(
                [
                    ("is_member", "=", True),
                    ("channel_type", "in", ("chat", "group", "channel")),
                    ("parent_channel_id", "=", False),
                ],
                order="last_interest_dt desc, id desc",
                limit=_RECENT_CONVERSATIONS,
            )
        )

    @staticmethod
    def _get_conversation_name(channel, user) -> str:
        """A direct chat is named after the others in it, not after `user`."""
        if channel.channel_type == "chat":
            others = channel.channel_member_ids.partner_id - user.partner_id
            if others:
                return ", ".join(others.mapped("name"))
        return channel.display_name

    def _offer_colleagues(self, bot, chat, user, term) -> None:
        tr = self._tr(bot, chat)
        term = (term or "").strip()
        colleagues = (
            self.env["res.users"]
            .with_user(user)
            .search(
                [
                    ("share", "=", False),
                    ("id", "!=", user.id),
                    ("name", "ilike", term),
                ],
                order="name",
                limit=_COLLEAGUES_SHOWN,
            )
            if term
            else self.env["res.users"]
        )
        if not colleagues:
            bot.send_message(
                chat.chat_id,
                tr._("No colleague is called %(name)s. Send /escribir to try again.")
                % {"name": tg.escape(term)},
            )
            return
        bot.send_message(
            chat.chat_id,
            tr._("Write to whom?"),
            parse_mode=None,
            reply_markup=kb.record_list(
                colleagues,
                lambda colleague: colleague.name,
                lambda colleague: f"mt:dm:{colleague.id}",
                width=60,
            ),
        )

    def _on_conversation_button(self, bot, chat, action, argument, user) -> None:
        tr = self._tr(bot, chat)
        if action == "new":
            chat._set_context(_PICK_KEY, True)
            bot.send_message(
                chat.chat_id,
                tr._("Who do you want to write to? Send their name."),
                parse_mode=None,
            )
            return
        if action == "end":
            chat._set_context(_FOCUS_KEY, False)
            bot.send_message(
                chat.chat_id,
                tr._("Done: what you write here no longer goes to that conversation."),
                parse_mode=None,
            )
            return
        channels = self.env["discuss.channel"].with_user(user)
        if action == "dm":
            colleague = (
                self.env["res.users"]
                .with_user(user)
                .search([("id", "=", int(argument or 0)), ("share", "=", False)])
            )
            if not colleague:
                return
            channel = channels._get_or_create_chat(partners_to=colleague.partner_id.ids)
        else:
            channel = channels.search(
                [("id", "=", int(argument or 0)), ("is_member", "=", True)]
            )
        if channel:
            self._open_focus(bot, chat, channel, user)

    # -- the open conversation ---------------------------------------------------

    def _open_focus(self, bot, chat, channel, user) -> None:
        """From now on what is written here goes to `channel`."""
        self._update_focus(chat, channel)
        tr = self._tr(bot, chat)
        bot.send_message(
            chat.chat_id,
            tr._(
                "✍️ You now write to %(name)s: what you send here goes to that "
                "conversation in Odoo, until you end it or an hour passes "
                "without writing."
            )
            % {"name": tg.bold(self._get_conversation_name(channel, user))},
            reply_markup=kb.single(tr._("⏹ End"), "mt:end"),
        )

    def _update_focus(self, chat, channel) -> None:
        chat._set_context(
            _FOCUS_KEY,
            {
                "channel_id": channel.id,
                "until": fields.Datetime.to_string(fields.Datetime.now() + _FOCUS_TTL),
            },
        )

    def _get_focus(self, chat, user):
        """The conversation what is written here goes to, as `user`, or None:
        none was opened, it went quiet, or `user` left it. A stale entry stays
        until the next one replaces it."""
        focus = chat._get_context(_FOCUS_KEY) or {}
        if not focus or not user:
            return None
        if fields.Datetime.to_datetime(focus.get("until")) <= fields.Datetime.now():
            return None
        channel = (
            self.env["discuss.channel"]
            .with_user(user)
            .search(
                [("id", "=", focus.get("channel_id") or 0), ("is_member", "=", True)]
            )
        )
        return channel or None

    # -- connecting -----------------------------------------------------------

    def _on_account_bound(self, bot, chat, binding) -> None:
        """Whoever just connected learns where their notifications go: here,
        when this bot delivers them to this account, and then here from now
        on; else what is missing."""
        user = chat.account_id._acting_user("internal")
        if not user:
            return
        tr = self._tr(bot, chat)
        if bot.notify_mail:
            refusal = self._get_chat_mail_refusal(bot, chat, user)
            if refusal:
                self._explain_mail_refusal(bot, chat, user, refusal)
                return
            user._update_telegram_notify_chat(chat)
            bot._queue_text(
                chat,
                tr._(
                    "Your Odoo notifications will arrive here. Reply to one to "
                    "answer it in Odoo."
                ),
                html=False,
            )
            return
        notifying = bot.env["telegram.bot"]._get_notifying_bots(user)
        reached = (
            bot.env["telegram.chat"]
            ._for_user(user, notifying)
            .filtered(lambda own: own.account_id == chat.account_id)
        )
        if not notifying or reached:
            return
        link = notifying[:1]._deep_link()
        if link:
            bot._queue_text(
                chat,
                tr._(
                    "Your Odoo notifications come from another bot: open "
                    "%(link)s and press Start."
                )
                % {"link": link},
                html=False,
            )

    def _on_phone_verified(self, bot, chat, account) -> None:
        """A number Telegram vouched for may be what the notifications were
        waiting for."""
        user = account._acting_user("internal")
        if not user or not bot.notify_mail:
            return
        refusal = self._get_chat_mail_refusal(bot, chat, user)
        if refusal:
            bot._queue_text(chat, refusal, html=False)
            return
        user._update_telegram_notify_chat(chat)
        bot._queue_text(
            chat,
            self._tr(bot, chat)._("Your Odoo notifications will arrive here."),
            html=False,
        )

    def _on_bot_membership(self, bot, chat, status):
        """Blocking the bot that delivers someone's notifications stops them:
        Odoo tells them, unless another chat of theirs takes over."""
        if status != "kicked" or chat.chat_type != "private" or not bot.notify_mail:
            return
        user = chat.account_id._acting_user("internal") if chat.account_id else None
        if not user:
            return
        target = user._get_telegram_notify_chat()
        if target and target != chat:
            return
        if not target and chat not in user._get_telegram_notify_chats():
            return
        user._notify_telegram_unreachable(
            chat,
            user.with_context(lang=user.lang).env._("you blocked the bot."),
        )

    # -- content --------------------------------------------------------------

    def _voice_text(self, bot, chat, message, user):
        """What a voice reply says, or None where voice notes cannot be heard
        (mail_speech_telegram hears them)."""
        return
