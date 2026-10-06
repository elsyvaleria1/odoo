import logging

import psycopg

from odoo import api, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import UserError

from ..tools import format as tg
from ..tools import replay
from ..tools.authority import operating
from ..tools.dispatch import message_kind, translation_env

_logger = logging.getLogger(__name__)

TOPIC_EVENTS = (
    "forum_topic_created",
    "forum_topic_edited",
    "forum_topic_closed",
    "forum_topic_reopened",
)
MEMBERSHIP_EVENTS = ("new_chat_members", "left_chat_member", "group_chat_created")

BUSY_CALLBACK_PREFIX = "tg_busy:"
HANDLER_PREFIX = "telegram.handler."


class ForeignSender(Exception):
    """A linked internal user who is no member of the company the bot speaks
    for: nothing runs on their behalf."""

    def __init__(self, chat):
        super().__init__(chat)
        self.chat = chat


class TelegramRouter(models.AbstractModel):
    """Every Telegram update goes through here, in one documented order.

    1. Rate limit, then the inbound log.
    2. A button press goes to the handler whose declared prefix its data
       carries (the flow-busy buttons are the router's own). It is always
       answered, so the client's spinner stops.
    3. A command goes to the handler declaring it, if the bot enables it, the
       sender's tier allows it, the handler agrees, and no other flow is open
       when it starts one.
    4. Any other message goes to the handler owning the chat's flow; else to
       a handler claiming it (a reply to something it sent); else to the idle
       intake for its kind -- the one the bot names, or the lowest priority
       among those accepting it.
    """

    _name = "telegram.router"
    _description = "Telegram Update Router"

    # -- handlers -------------------------------------------------------------

    @api.model
    def _handler_names(self):
        return sorted(
            name
            for name in self.env.registry
            if name.startswith(HANDLER_PREFIX)
            and isinstance(self.env[name], self.env.registry["mixin.telegram.handler"])
        )

    @api.model
    def _handlers(self, bot=None):
        handlers = [self.env[name] for name in self._handler_names()]
        if bot is not None:
            handlers = [h for h in handlers if h._feature_enabled(bot)]
        return handlers

    @api.model
    def _check_handler_declarations(self) -> tuple:
        """Refuse two handlers claiming one command or one callback prefix:
        which one answered would otherwise depend on nothing anybody chose."""
        commands, prefixes = {}, {}
        for handler in self._handlers():
            for command in handler._telegram_commands():
                if command in commands:
                    raise ValueError(
                        f"Telegram command {command} is declared by both "
                        f"{commands[command]} and {handler._name}"
                    )
                commands[command] = handler._name
            for prefix in handler._telegram_callback_prefixes():
                for other, owner in prefixes.items():
                    if prefix.startswith(other) or other.startswith(prefix):
                        raise ValueError(
                            f"Telegram callback prefix {prefix!r} of {handler._name} "
                            f"overlaps {other!r} of {owner}"
                        )
                prefixes[prefix] = handler._name
        return commands, prefixes

    def _register_hook(self):
        super()._register_hook()
        self._check_handler_declarations()

    @api.model
    def _command_owner(self, bot, command) -> tuple:
        for handler in self._handlers():
            spec = handler._telegram_commands().get(command)
            if spec:
                return handler, spec
        return None, None

    @api.model
    def _intake_selection(self, kind) -> list:
        handlers = [h for h in self._handlers() if kind in h._telegram_intakes()]
        return [(h._name, h._description) for h in handlers]

    # -- update ---------------------------------------------------------------

    @api.model
    def _handle_update(self, bot, data) -> None:
        # the webhook hands over a superuser bot: an update runs as the
        # request's own user, keeping the bot's records by the privilege
        bot = operating(bot.with_env(bot.env(su=False)))
        self = self.with_env(bot.env)
        update_id = data.get("update_id")
        chats = bot.env["telegram.chat"]
        chats._discard_activity()
        replay.begin_update((bot.id, update_id) if update_id else None)
        try:
            try:
                self._dispatch_update(bot, data)
            except ForeignSender as refused:
                self._refuse_foreign_sender(bot, refused.chat, data)
            chats._flush_activity()
        finally:
            chats._discard_activity()
            if not update_id:
                replay.end_update()

    @api.model
    def _dispatch_update(self, bot, data) -> None:
        if "message" in data:
            self._dispatch_message(bot, data["message"])
        elif "callback_query" in data:
            self._dispatch_callback_query(bot, data["callback_query"])
        elif "edited_message" in data:
            self._dispatch_edited_message(bot, data["edited_message"])
        elif "my_chat_member" in data:
            self._dispatch_my_chat_member(bot, data["my_chat_member"])
        elif "business_connection" in data:
            self._dispatch_business_connection(bot, data["business_connection"])
        elif "business_message" in data:
            self._dispatch_business_message(bot, data["business_message"])
        elif "edited_business_message" in data:
            self._dispatch_business_message(
                bot, data["edited_business_message"], edited=True
            )
        elif "deleted_business_messages" in data:
            self._dispatch_business_deleted(bot, data["deleted_business_messages"])
        elif "channel_post" in data:
            self._dispatch_channel_post(bot, data["channel_post"])
        elif "message_reaction" in data:
            self._dispatch_message_reaction(bot, data["message_reaction"])
        else:
            _logger.debug(
                "Update %s carries no message or callback_query, ignoring",
                data.get("update_id"),
            )

    @api.model
    def _refuse_foreign_sender(self, bot, chat, data) -> None:
        # an edit or a reaction is dropped unanswered: only what asked for
        # something is told why nothing happens
        _logger.info(
            "Chat %s: the linked user is no member of bot %s's company, refused",
            chat.id,
            bot.id,
        )
        if "callback_query" in data:
            bot.answer_callback_query(data["callback_query"].get("id"))
        elif "message" not in data:
            return
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "Your Odoo user is not a member of the company this bot speaks "
                "for, so it cannot act for you here. Ask an administrator to add "
                "you to that company, or write to your own company's bot."
            ),
        )

    @api.model
    def _as_sender(self, internal_user, bot, chat, *records):
        """The router, `bot`, `chat` and `records` as the update's sender: a
        linked internal user in a private chat acts as themself -- a command,
        a button, a message alike -- in the bot's company and no other, and
        anyone else as the request's own user. The bot keeps its records by
        the privilege either way. A linked internal user who is no member of
        the bot's company raises ForeignSender."""
        records = (self, bot, chat, *records)
        if not internal_user:
            return records
        if not bot._admits_user(internal_user):
            raise ForeignSender(chat)
        sender_env = self.env(
            user=internal_user,
            context={**self.env.context, "allowed_company_ids": [bot.company_id.id]},
        )
        # the sender is who really acts from here on: the guards that ask the
        # transaction for its real user (x2many links to users and partners)
        # must see them, not the request's public user
        self.env.transaction.default_env = sender_env
        env = operating(self.with_env(sender_env)).env
        return tuple(record.with_env(env) for record in records)

    @api.model
    def _acquire_chat_and_identity(self, bot, message_or_callback):
        """The chat, and who the update may act as: resolved from the sender's
        Telegram account and its active binding, and only in a private chat --
        a group has many speakers and whatever runs there answers to all of
        them, so it is served as unlinked."""
        is_callback = "data" in message_or_callback
        if is_callback:
            chat_data = message_or_callback.get("message", {}).get("chat", {})
        else:
            chat_data = message_or_callback.get("chat", {})
        chat_type = chat_data.get("type")
        account = bot.env["telegram.account"]._from_telegram(
            message_or_callback.get("from")
        )
        chat = bot.env["telegram.chat"]._acquire_chat(
            chat_data.get("id"),
            bot.id,
            chat_type=chat_type,
            account=account,
        )
        title = chat_data.get("title")
        if title and chat.title != title:
            chat.title = title
        partner = bot.env["res.partner"]
        internal_user = False
        if chat_type == "private" and account and chat.account_id == account:
            partner = account._acting_partner()
            internal_user = account._acting_user("internal") or False
        _logger.debug(
            "Update routed to chat %s (account %s, partner %s, user %s)",
            chat.id,
            account.id or "-",
            partner.id or "-",
            internal_user.id if internal_user else "-",
        )
        return chat, partner, internal_user

    @staticmethod
    def _normalize_command_token(text):
        if not text:
            return ""
        token = text.replace("\xa0", " ").split()[0]
        return token.split("@")[0].rstrip(".!")

    @staticmethod
    def _addressed_elsewhere(bot, text) -> bool:
        """Whether a command names another bot (`/start@other_bot`), as a
        group's members write to pick one of its bots."""
        if not text.startswith("/"):
            return False
        _command, _at, username = text.split(maxsplit=1)[0].partition("@")
        return bool(username) and username.lower() != (bot.bot_username or "").lower()

    @classmethod
    def _split_command(cls, text) -> tuple:
        command = cls._normalize_command_token(text)
        remainder = text.replace("\xa0", " ").split(maxsplit=1)
        args = remainder[1].split() if len(remainder) > 1 else []
        return command, args

    @api.model
    def _log_inbound_message(self, bot, chat, message, message_text) -> None:
        msg_uid = str(message.get("message_id")) if message.get("message_id") else False
        if not msg_uid:
            return
        messages = bot.env["telegram.message"]
        existing = messages.search(
            [
                ("bot_id", "=", bot.id),
                ("chat_id", "=", chat.id),
                ("msg_uid", "=", msg_uid),
            ],
            limit=1,
        )
        if existing:
            _logger.debug("Message %s already exists, skipping creation", msg_uid)
            return
        kind = message_kind(message)
        vals = {
            "bot_id": bot.id,
            "chat_id": chat.id,
            "text": message_text,
            "caption": message.get("caption") or False,
            "media_type": kind if kind in ("photo", "document", "voice") else "text",
            "message_type": "inbound",
            "state": "received",
            "msg_uid": msg_uid,
            "reply_to_uid": str(
                (message.get("reply_to_message") or {}).get("message_id") or ""
            )
            or False,
        }
        if message_text.startswith("/"):
            vals["command"] = self._normalize_command_token(message_text)
        if message.get("is_topic_message") and message.get("message_thread_id"):
            vals["thread_uid"] = str(message["message_thread_id"])
        try:
            with bot.env.cr.savepoint():
                messages.create(vals)
        except (UserError, psycopg.Error) as e:
            _logger.warning(
                "Failed to create message record (msg_uid=%s): %s", msg_uid, e
            )

    @api.model
    def _notify_rate_limited(self, bot, chat) -> None:
        if not chat._consume_rate_limit_notice():
            _logger.debug("Chat %s is still rate limited, staying quiet", chat.id)
            return
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "You have reached the message limit. Please wait a moment."
            ),
        )

    # -- messages -------------------------------------------------------------

    @api.model
    def _dispatch_message(self, bot, message) -> None:
        if message.get("from", {}).get("is_bot"):
            _logger.debug("Skipping message from bot user to prevent loop")
            return
        if self._dispatch_service_message(bot, message):
            return
        if self._addressed_elsewhere(bot, message.get("text", "")):
            return
        chat, partner, internal_user = self._acquire_chat_and_identity(bot, message)
        self, bot, chat, partner = self._as_sender(internal_user, bot, chat, partner)
        if chat.chat_type in ("group", "supergroup"):
            command, args = self._split_command(message.get("text", ""))
            if command == "/start" and args:
                self._dispatch_group_link(bot, chat, message, args[0])
                return
        if not chat._consume_rate_limit():
            self._notify_rate_limited(bot, chat)
            return
        message_text = message.get("text", "")
        self._log_inbound_message(bot, chat, message, message_text)
        if message_text.startswith("/"):
            command, args = self._split_command(message_text)
            self._dispatch_command(bot, chat, command, args, partner, internal_user)
            return
        self._dispatch_free_message(bot, chat, message, partner, internal_user)

    @api.model
    def _dispatch_free_message(
        self, bot, chat, message, partner, internal_user
    ) -> None:
        # a flow belongs to the handler that opened it, enabled on this bot or
        # not: a Mini App can open one on any bot
        owner = self._flow_owner(chat)
        if owner is not None and self._run_message_handler(
            owner, bot, chat, message, partner, internal_user
        ):
            return
        if owner is None:
            for handler in self._handlers(bot):
                if handler._claims_message(
                    bot, chat, message, partner, internal_user
                ) and self._run_message_handler(
                    handler, bot, chat, message, partner, internal_user
                ):
                    return
            idle = self._idle_handler(bot, chat, message, partner, internal_user)
            if idle is not None and self._run_message_handler(
                idle, bot, chat, message, partner, internal_user
            ):
                return
        self._unhandled_message(bot, chat, message, partner, internal_user)

    @api.model
    def _idle_handler(self, bot, chat, message, partner, internal_user):
        kind = message_kind(message)
        accepting = [
            h
            for h in self._handlers(bot)
            if h._accepts_idle(bot, chat, kind, message, partner, internal_user)
        ]
        if not accepting:
            return None
        chosen = bot._idle_handler_name(kind)
        if chosen:
            named = [h for h in accepting if h._name == chosen]
            if named:
                return named[0]
        accepting.sort(key=lambda h: (h._telegram_intake_priority, h._name))
        if len(accepting) > 1 and not chosen:
            _logger.warning(
                "Bot %s: %s all take an idle %s message; %s answers. Name one on "
                "the bot to decide.",
                bot.id,
                [h._name for h in accepting],
                kind,
                accepting[0]._name,
            )
        return accepting[0]

    @api.model
    def _run_message_handler(self, handler, bot, chat, message, partner, internal_user):
        try:
            with bot.env.cr.savepoint():
                return handler._on_message(bot, chat, message, partner, internal_user)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception as error:
            _logger.exception("Handler %s failed on a message", handler._name)
            self._recover_from_handler_failure(bot, chat, None, error)
            return True

    @api.model
    def _unhandled_message(self, bot, chat, message, partner, internal_user) -> None:
        owner = self._flow_owner(chat)
        if owner is not None:
            self._send_flow_busy_notice(bot, chat, owner, trigger="message")
            return
        bot.send_message(
            chat.chat_id,
            translation_env(bot, chat)._(
                "Sorry, I can only process commands. Type /ayuda to see the list."
            ),
        )

    @api.model
    def _dispatch_edited_message(self, bot, message) -> None:
        """A message its sender edited: the ledger row follows, and the handler
        that acted on it may update what it made of it."""
        if message.get("from", {}).get("is_bot"):
            return
        chat, partner, internal_user = self._acquire_chat_and_identity(bot, message)
        self, bot, chat, partner = self._as_sender(internal_user, bot, chat, partner)
        ledger = bot.env["telegram.message"].search(
            [
                ("bot_id", "=", bot.id),
                ("chat_id", "=", chat.id),
                ("msg_uid", "=", str(message.get("message_id") or "")),
                ("message_type", "=", "inbound"),
            ],
            limit=1,
        )
        if not ledger:
            return
        ledger.write(
            {
                "text": message.get("text") or ledger.text,
                "caption": message.get("caption") or ledger.caption,
            }
        )
        for handler in self._handlers():
            if handler._on_edited_message(
                bot, chat, message, ledger, partner, internal_user
            ):
                return

    @api.model
    def _dispatch_my_chat_member(self, bot, update) -> None:
        """The bot's own membership changed: blocked or unblocked in a private
        chat, added to or removed from a group."""
        chat_data = update.get("chat") or {}
        status = (update.get("new_chat_member") or {}).get("status")
        chat = bot.env["telegram.chat"]._acquire_chat(
            chat_data.get("id"), bot.id, chat_type=chat_data.get("type")
        )
        blocked = status in ("kicked", "left")
        if chat.bot_blocked != blocked:
            chat.bot_blocked = blocked
        _logger.info("Bot %s is now %s in chat %s", bot.id, status, chat.id)
        for handler in self._handlers():
            handler._on_bot_membership(bot, chat, status)

    # -- groups ---------------------------------------------------------------

    @api.model
    def _dispatch_service_message(self, bot, message) -> bool:
        """What Telegram says about a group rather than in it: a migration to
        a supergroup, a forum topic's life, members coming and going. True
        when the message is one of those."""
        chat_data = message.get("chat") or {}
        chats = bot.env["telegram.chat"]
        if message.get("migrate_to_chat_id"):
            group = chats._acquire_chat(chat_data.get("id"), bot.id)
            group._migrate_to(message["migrate_to_chat_id"])
            return True
        if message.get("migrate_from_chat_id"):
            group = chats._acquire_chat(message["migrate_from_chat_id"], bot.id)
            group._migrate_to(chat_data.get("id"))
            return True
        topic_event = next((key for key in TOPIC_EVENTS if key in message), None)
        if topic_event:
            chat = chats._acquire_chat(
                chat_data.get("id"), bot.id, chat_type=chat_data.get("type")
            )
            for handler in self._handlers():
                if handler._on_forum_topic(
                    bot,
                    chat,
                    str(message.get("message_thread_id") or ""),
                    topic_event,
                    message[topic_event] or {},
                ):
                    break
            return True
        return any(key in message for key in MEMBERSHIP_EVENTS)

    @api.model
    def _dispatch_group_link(self, bot, chat, message, token) -> None:
        """`/start <token>` in a group: what `?startgroup=<token>` makes
        Telegram send when someone adds the bot. The token names what Odoo
        links the group to; the person adding the bot must be the Odoo user
        who made the link, and an administrator of the group."""
        tr_env = translation_env(bot, chat)
        account = bot.env["telegram.account"]._from_telegram(message.get("from"))
        link = bot.env["telegram.link.token"]._consume(
            bot, token, account, purpose="group"
        )
        refusal = None
        if not link:
            refusal = tr_env._(
                "This link is expired or was already used. Create a new one in Odoo."
            )
        elif not account or account._acting_user("internal") != link.user_id:
            refusal = tr_env._(
                "Only the Odoo user who created this link can connect the group, "
                "from the Telegram account connected to them."
            )
        elif not bot._is_chat_administrator(chat, account.tg_user_id):
            refusal = tr_env._("Only an administrator of the group can connect it.")
        if refusal:
            bot.send_message(chat.chat_id, refusal, parse_mode=None)
            return
        for handler in self._handlers():
            if handler._on_group_link(bot, chat, link, account):
                return
        _logger.warning(
            "Group link %s for %s,%s found no handler",
            link.id,
            link.res_model,
            link.res_id,
        )

    @api.model
    def _dispatch_channel_post(self, bot, post) -> None:
        """A post in a Telegram channel the bot administers. The bot publishes
        there and reads nothing but `/start <token>`, which connects the
        channel to what the token names: channel posts have no sender, so the
        token's own user must be an administrator of the channel, from the
        Telegram account connected to them."""
        text = post.get("text") or ""
        if self._addressed_elsewhere(bot, text):
            return
        command, args = self._split_command(text)
        if command != "/start" or not args:
            return
        chat_data = post.get("chat") or {}
        chats = bot.env["telegram.chat"]
        chat = chats._acquire_chat(chat_data.get("id"), bot.id, chat_type="channel")
        if chat_data.get("title") and chat.title != chat_data["title"]:
            chat.title = chat_data["title"]
        link = bot.env["telegram.link.token"]._consume(
            bot, args[0], bot.env["telegram.account"], purpose="broadcast"
        )
        if not link:
            return
        # the post showed a token to every subscriber: it goes either way
        bot.env["telegram.message"]._queue(
            bot, chat, "deleteMessage", {"message_id": post.get("message_id")}
        )
        own_chat = bot.env["telegram.chat"]._for_user(link.user_id, bot)[:1]
        account = own_chat.account_id
        if not account or not bot._is_chat_administrator(chat, account.tg_user_id):
            # a channel's subscribers would read an answer there
            if own_chat:
                bot.send_message(
                    own_chat.chat_id,
                    translation_env(bot, own_chat)._(
                        "The channel %(title)s was not connected: post the link "
                        "there as one of its administrators, from this Telegram "
                        "account."
                    )
                    % {"title": chat.title or chat.chat_id},
                    parse_mode=None,
                )
            return
        for handler in self._handlers():
            if handler._on_channel_link(bot, chat, link, account):
                return

    @api.model
    def _dispatch_message_reaction(self, bot, update) -> None:
        """Someone changed their reactions to a message the ledger holds:
        what they added and what they took back, as emoji."""
        chat_data = update.get("chat") or {}
        chat = bot.env["telegram.chat"].search(
            [
                ("chat_id", "=", str(chat_data.get("id"))),
                ("bot_id", "=", bot.id),
                ("business_connection_id", "=", False),
            ],
            limit=1,
        )
        account = bot.env["telegram.account"]._from_telegram(update.get("user"))
        ledger = bot.env["telegram.message"].search(
            [
                ("chat_id", "=", chat.id),
                ("msg_uid", "=", str(update.get("message_id") or "")),
            ],
            limit=1,
        )
        if not chat or not account or not ledger:
            return
        if chat.chat_type == "private" and chat.account_id == account:
            self, bot, chat, ledger, account = self._as_sender(
                account._acting_user("internal"), bot, chat, ledger, account
            )

        def emoji(reactions):
            return {
                reaction["emoji"]
                for reaction in reactions or ()
                if reaction.get("type") == "emoji" and reaction.get("emoji")
            }

        old, new = emoji(update.get("old_reaction")), emoji(update.get("new_reaction"))
        for handler in self._handlers():
            if handler._on_reaction(
                bot, chat, ledger, account, added=new - old, removed=old - new
            ):
                return

    @api.model
    def _chat_migrated(self, bot, group, supergroup) -> None:
        for handler in self._handlers():
            handler._on_chat_migrated(bot, group, supergroup)

    # -- business accounts ----------------------------------------------------

    @api.model
    def _dispatch_business_connection(self, bot, data) -> None:
        connection = bot.env["telegram.business.connection"]._from_update(bot, data)
        if (
            connection.is_enabled
            and not connection.user_id
            and data.get("user_chat_id")
        ):
            owner_chat = bot.env["telegram.chat"]._acquire_chat(
                data["user_chat_id"],
                bot.id,
                chat_type="private",
                account=connection.account_id,
            )
            bot.send_message(
                owner_chat.chat_id,
                translation_env(bot, owner_chat)._(
                    "Connect this Telegram account to your Odoo user before the "
                    "bot answers your business chats: in Odoo, open My "
                    "Preferences and press Connect Telegram."
                ),
                parse_mode=None,
            )

    @api.model
    def _business_connection_of(self, bot, uid):
        connection = bot.env["telegram.business.connection"].search(
            [("bot_id", "=", bot.id), ("connection_uid", "=", uid)], limit=1
        )
        return connection if connection and connection._usable() else None

    @api.model
    def _dispatch_business_message(self, bot, message, edited=False) -> None:
        """A message in a chat of a business account the bot manages: from
        the customer, or from the owner writing on their phone."""
        connection = self._business_connection_of(
            bot, message.get("business_connection_id")
        )
        if connection is None:
            return
        chat_data = message.get("chat") or {}
        sender = bot.env["telegram.account"]._from_telegram(message.get("from"))
        from_owner = sender == connection.account_id
        customer = (
            bot.env["telegram.account"]._from_telegram(chat_data)
            if from_owner
            else sender
        )
        chat = bot.env["telegram.chat"]._acquire_chat(
            chat_data.get("id"),
            bot.id,
            chat_type="private",
            account=customer,
            business_connection=connection,
        )
        self._log_inbound_message(bot, chat, message, message.get("text", ""))
        for handler in self._handlers(bot):
            if handler._on_business_message(
                bot, connection, chat, message, from_owner, edited
            ):
                return

    @api.model
    def _dispatch_business_deleted(self, bot, data) -> None:
        connection = self._business_connection_of(
            bot, data.get("business_connection_id")
        )
        if connection is None:
            return
        chat = bot.env["telegram.chat"].search(
            [
                ("chat_id", "=", str((data.get("chat") or {}).get("id"))),
                ("bot_id", "=", bot.id),
                ("business_connection_id", "=", connection.id),
            ],
            limit=1,
        )
        if not chat:
            return
        ledgers = bot.env["telegram.message"].search(
            [
                ("chat_id", "=", chat.id),
                ("msg_uid", "in", [str(uid) for uid in data.get("message_ids") or []]),
            ]
        )
        for handler in self._handlers(bot):
            if handler._on_business_deleted(bot, connection, chat, ledgers):
                return

    # -- commands -------------------------------------------------------------

    @api.model
    def _is_command_enabled(self, bot, command, spec) -> bool:
        return bool(spec.builtin or command in bot.command_ids.mapped("name"))

    @staticmethod
    def _tier_allows(tier, partner, internal_user) -> bool:
        if tier == "unlinked":
            return True
        if tier == "partner":
            return bool(partner)
        return bool(internal_user)

    @api.model
    def _dispatch_command(
        self, bot, chat, command, args, partner, internal_user
    ) -> None:
        tr_env = translation_env(bot, chat)
        handler, spec = self._command_owner(bot, command)
        if not spec or not self._is_command_enabled(bot, command, spec):
            bot.send_message(
                chat.chat_id,
                tr_env._("Unknown command: %(command)s. Type /ayuda to see the list.")
                % {"command": tg.code(command)},
            )
            return
        if not self._tier_allows(spec.tier, partner, internal_user):
            if not partner:
                msg = tr_env._(
                    "To use the command %(command)s connect your Telegram account "
                    "to Odoo: in Odoo, open My Preferences and press Connect "
                    "Telegram, or ask an administrator for an invitation."
                ) % {"command": tg.code(command)}
            else:
                msg = tr_env._(
                    "You don't have permission to use the command %(command)s."
                ) % {"command": tg.code(command)}
            bot.send_message(chat.chat_id, msg)
            return
        if not handler._command_allowed(bot, chat, command, partner, internal_user):
            return
        if spec.starts_flow:
            owner = self._flow_owner(chat)
            if owner is not None:
                self._send_flow_busy_notice(bot, chat, owner, command)
                return
        try:
            with bot.env.cr.savepoint():
                self._run_command_handler(
                    handler, spec.method, bot, chat, args, partner, internal_user
                )
        except PG_RETRY_EXCEPTIONS:
            # Not the user's fault and not worth a failure counter: the request
            # retry loop replays the whole update on a fresh transaction.
            _logger.info(
                "Command handler '%s' hit a concurrency conflict, letting it retry",
                command,
            )
            raise
        except Exception as e:
            _logger.exception("Command handler '%s' failed", command)
            self._recover_from_handler_failure(bot, chat, command, e)
            return
        chat._reset_failed_state()

    @api.model
    def _run_command_handler(
        self, handler, method_name, bot, chat, args, partner, internal_user
    ):
        _logger.info(
            "Dispatching command as %s",
            f"internal user {internal_user.id}"
            if internal_user
            else ("partner" if partner else "unlinked user"),
        )
        return getattr(handler, method_name)(
            bot, chat, args, partner=partner or False, internal_user=internal_user
        )

    @api.model
    def _recover_from_handler_failure(self, bot, chat, command, error) -> None:
        chat.invalidate_recordset()
        chat._flow_end()
        failures = chat._increment_failed_state(str(error))
        tr_env = translation_env(bot, chat)
        if failures >= 3:
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "It seems you're having trouble. Type /ayuda to see available "
                    "commands."
                ),
            )
            chat._reset_failed_state()
        else:
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "An error occurred while processing your command. Please try again."
                ),
            )

    # -- buttons --------------------------------------------------------------

    @api.model
    def _dispatch_callback_query(self, bot, callback_query) -> None:
        chat, partner, internal_user = self._acquire_chat_and_identity(
            bot, callback_query
        )
        self, bot, chat, partner = self._as_sender(internal_user, bot, chat, partner)
        if not chat._consume_rate_limit():
            self._notify_rate_limited(bot, chat)
            return
        data = callback_query.get("data") or ""
        answered = replay.begin_callback()
        try:
            if data.startswith(BUSY_CALLBACK_PREFIX):
                self._handle_flow_busy_callback(
                    bot, chat, callback_query, partner, internal_user
                )
                return
            handler = self._callback_owner(bot, data)
            if handler is not None and handler._on_callback(
                bot, chat, callback_query, partner, internal_user
            ):
                return
            bot.send_message(
                chat.chat_id,
                translation_env(bot, chat)._(
                    "I received an action, but I don't know how to process it."
                ),
            )
        finally:
            if callback_query.get("id") and callback_query["id"] not in answered:
                bot.answer_callback_query(callback_query["id"])

    @api.model
    def _callback_owner(self, bot, data):
        # a button belongs to the handler that sent it, whatever the bot runs
        # now: messages already sent keep working
        best, length = None, -1
        for handler in self._handlers():
            for prefix in handler._telegram_callback_prefixes():
                if data.startswith(prefix) and len(prefix) > length:
                    best, length = handler, len(prefix)
        return best

    # -- flows ----------------------------------------------------------------

    @api.model
    def _flow_owner(self, chat):
        """The handler whose flow the chat is in, else None."""
        if not chat._flow_is_open():
            return None
        handler = self.env[chat.flow_owner]
        if not isinstance(handler, self.env.registry["mixin.telegram.handler"]):
            return None
        return handler

    @api.model
    def _cancel_flow(self, bot, chat):
        """End the chat's flow, whoever owns it, after its owner cleaned up;
        the owner it had, else None."""
        owner = self._flow_owner(chat)
        if owner is not None:
            owner._on_flow_cancelled(bot, chat)
        chat._flow_end()
        return owner

    @api.model
    def _flow_starting_commands(self) -> set:
        return {
            command
            for handler in self._handlers()
            for command, spec in handler._telegram_commands().items()
            if spec.starts_flow
        }

    @api.model
    def _send_flow_busy_notice(
        self, bot, chat, owner, command=None, trigger="button"
    ) -> None:
        tr_env = translation_env(bot, chat)
        lines = [
            tr_env._("⚠️ You already have %(flow)s in progress.")
            % {"flow": tg.escape(owner._telegram_flow_label(bot, chat))},
            "",
        ]
        if command:
            lines.append(
                tr_env._(
                    "Finish what you have going before using %(command)s, or choose an "
                    "option:"
                )
                % {"command": tg.code(command)}
            )
        elif trigger == "message":
            lines.append(
                tr_env._(
                    "Finish what you have going by replying to my last message, or "
                    "discard it with the button below."
                )
            )
        else:
            lines.append(
                tr_env._(
                    "Discard what you have going or finish it, then tap the button "
                    "again."
                )
            )
        lines.append("")
        lines.append(
            tr_env._("You can also type %(command)s to cancel it.")
            % {"command": tg.code("/cancelar")}
        )
        if command:
            buttons = [
                [
                    {
                        "text": tr_env._("▶️ Continue what I have going"),
                        "callback_data": f"{BUSY_CALLBACK_PREFIX}keep",
                    }
                ],
                [
                    {
                        "text": tr_env._("🗑 Discard and start over"),
                        "callback_data": f"{BUSY_CALLBACK_PREFIX}restart:{command}",
                    }
                ],
            ]
        else:
            discard = "discard:message" if trigger == "message" else "discard"
            buttons = [
                [
                    {
                        "text": tr_env._("🗑 Discard what I have going"),
                        "callback_data": f"{BUSY_CALLBACK_PREFIX}{discard}",
                    }
                ]
            ]
        bot.send_message(
            chat.chat_id, "\n".join(lines), reply_markup={"inline_keyboard": buttons}
        )
        if command:
            refused = command
        elif trigger == "message":
            refused = "a plain message"
        else:
            refused = "an inline-button flow"
        _logger.info(
            "Chat %s refused '%s': flow %s is open at %s",
            chat.id,
            refused,
            chat.flow_owner,
            chat.flow_step,
        )

    @api.model
    def _handle_flow_busy_callback(
        self, bot, chat, callback_query, partner, internal_user
    ) -> None:
        tr_env = translation_env(bot, chat)
        bot.answer_callback_query(callback_query.get("id"))
        self.env["mixin.telegram.handler"]._clear_keyboard(bot, chat, callback_query)
        action = (callback_query.get("data") or "")[len(BUSY_CALLBACK_PREFIX) :]
        if action == "keep":
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "Go ahead, pick up where you left off. Reply to my last message."
                ),
            )
            return
        if action.startswith("discard"):
            self._cancel_flow(bot, chat)
            if action == "discard:message":
                notice = tr_env._("Done, I discarded it. Tell me again what you need.")
            else:
                notice = tr_env._(
                    "Done, I discarded it. Tap the button you wanted again."
                )
            bot.send_message(chat.chat_id, notice)
            return
        command = action.removeprefix("restart:")
        if (
            not action.startswith("restart:")
            or command not in self._flow_starting_commands()
        ):
            _logger.warning(
                "Chat %s sent an unknown flow-busy action '%s'", chat.id, action
            )
            return
        self._cancel_flow(bot, chat)
        bot.send_message(
            chat.chat_id, tr_env._("Done, I discarded the previous one. Starting over.")
        )
        self._dispatch_command(bot, chat, command, [], partner, internal_user)

    @api.model
    def _flow_guard_blocks(self, bot, chat, data=None) -> bool:
        """Whether an open flow refuses a button press: the flow's owner may
        use its own buttons, nothing else runs until it ends."""
        owner = self._flow_owner(chat)
        if owner is None:
            return False
        button_owner = self._callback_owner(bot, data or "")
        if button_owner is not None and button_owner._name == owner._name:
            return False
        self._send_flow_busy_notice(bot, chat, owner)
        return True

    # -- help -----------------------------------------------------------------

    @api.model
    def _help_sections(self, bot, partner, internal_user, chat=None):
        sections = []
        for handler in self._handlers(bot):
            sections.extend(
                handler._get_help_sections(bot, partner, internal_user, chat=chat)
            )
        return sections
