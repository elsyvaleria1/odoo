from datetime import timedelta

from markupsafe import Markup, escape

from odoo import models

from ..tools.dispatch import translation_env

# What a message carries as files, and the name each gets without its own.
_FILES = (
    ("photo", "photo.jpg"),
    ("document", "document"),
    ("voice", "voice.ogg"),
    ("audio", "audio"),
    ("video", "video.mp4"),
)


class MixinTelegramHandler(models.AbstractModel):
    """What a feature answers on a Telegram bot.

    A handler is an abstract model named `telegram.handler.<feature>`; the
    router finds every installed one in the database's registry, so what a
    bot answers depends on the database's modules and never on which Python
    classes a process happened to import. A handler declares -- it never
    decides the order it is asked in:

      - its commands (`_telegram_commands`), with the tier they need;
      - the callback-data prefixes of its buttons: two handlers claiming one
        prefix fail the registry load;
      - what its multi-step flows are called (`_telegram_flow_label`): a
        flow it opens on a chat is its own, gets that chat's free text and
        nobody else's, and ends by its own step, by expiring, or by /cancelar;
      - the message kinds it takes from an idle chat (text, voice, photo,
        document, contact, location): when several do, the bot says which,
        else the lowest `_telegram_intake_priority` wins.

    Extending a handler is Odoo inheritance: `_inherit` it and call super().
    """

    _name = "mixin.telegram.handler"
    _description = "Telegram Handler"

    _telegram_intake_priority = 100
    _telegram_flow_ttl = timedelta(hours=1)

    def _telegram_commands(self) -> dict:
        """{"/command": TelegramCommand(...)} this handler answers."""
        return {}

    def _telegram_callback_prefixes(self):
        return ()

    def _telegram_intakes(self):
        return frozenset()

    def _feature_enabled(self, bot):
        """Whether the bot runs this feature: by default, whether any of its
        commands is linked to the bot, or it has none."""
        commands = self._telegram_commands()
        if not commands:
            return True
        linked = set(bot.command_ids.mapped("name"))
        return bool(linked & set(commands))

    # -- flows ----------------------------------------------------------------

    def _telegram_flow_label(self, bot, chat):
        """What the chat has going while this handler's flow is open, as the
        busy notice names it."""
        return self._tr(bot, chat)._("an operation")

    def _on_flow_cancelled(self, bot, chat):
        """The person cancelled this handler's open flow; its data is still on
        the chat and the flow ends when this returns."""

    def _owns_flow(self, chat):
        return chat._flow_is_open() and chat.flow_owner == self._name

    def _flow_step(self, chat):
        return chat.flow_step if self._owns_flow(chat) else False

    def _flow_data(self, chat):
        return dict(chat.flow_data or {}) if self._owns_flow(chat) else {}

    def _flow_start(self, chat, step, data=None) -> None:
        chat._flow_start(self._name, step, data)

    def _flow_end(self, chat) -> None:
        """End the chat's flow if it is this handler's; another handler's
        flow is not this one's to end."""
        if chat.flow_owner == self._name:
            chat._flow_end()

    def _claims_message(self, bot, chat, message, partner, internal_user) -> bool:
        """Whether this handler takes a message outside any flow before the
        idle intake is asked -- a reply to a message it sent, for instance."""
        return False

    def _accepts_idle(self, bot, chat, kind, message, partner, internal_user):
        return kind in self._telegram_intakes()

    def _on_message(self, bot, chat, message, partner, internal_user):
        """Handle a non-command message; True when it was consumed."""
        return False

    def _on_edited_message(
        self, bot, chat, message, ledger, partner, internal_user
    ) -> bool:
        """A message its sender edited, whose inbound ledger row is `ledger`;
        True when this handler updated what it had made of it."""
        return False

    def _on_group_link(self, bot, chat, link, account) -> bool:
        """A group was connected with a link token naming a record of this
        handler's; True when it took it."""
        return False

    def _on_channel_link(self, bot, chat, link, account) -> bool:
        """A Telegram channel was connected with a link token naming a record
        of this handler's; True when it took it."""
        return False

    def _on_forum_topic(self, bot, chat, thread_uid, event, data) -> bool:
        """A forum topic of the group was created, edited, closed or
        reopened; True when handled."""
        return False

    def _on_reaction(self, bot, chat, ledger, account, *, added, removed) -> bool:
        """`account` reacted to the message `ledger` holds: emoji `added` and
        `removed`; True when handled."""
        return False

    def _on_chat_migrated(self, bot, group, supergroup):
        """A group became a supergroup, which is a new chat."""

    def _on_bot_membership(self, bot, chat, status):
        """The bot's own status in the chat changed: member, administrator,
        left, kicked."""

    def _on_account_bound(self, bot, chat, binding) -> None:
        """The person of the private chat `chat` just proved who they are in
        Odoo through `bot`: `binding` is who their account is now. Every
        handler hears it, enabled on the bot or not."""

    def _on_phone_verified(self, bot, chat, account) -> None:
        """The person of the private chat `chat` shared their own number,
        which Telegram vouched for: `account.phone` is it now. Every handler
        hears it, enabled on the bot or not."""

    def _on_business_message(
        self, bot, connection, chat, message, from_owner, edited
    ) -> bool:
        """A message in a chat of a Telegram Business account the bot manages
        -- the customer's, or the owner's own from their phone; True when
        handled."""
        return False

    def _on_business_deleted(self, bot, connection, chat, ledgers) -> bool:
        """Messages the owner or customer deleted in a business chat, as the
        ledger rows they had; True when handled."""
        return False

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        """Handle a button press whose data carries one of this handler's
        prefixes; True when it was consumed."""
        return False

    def _command_allowed(self, bot, chat, command, partner, internal_user) -> bool:
        return True

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        return []

    def _tr(self, bot, chat=None):
        return translation_env(bot, chat)

    @staticmethod
    def _chat_internal_user(chat):
        """The internal user a private chat's person acts as, else no user."""
        if chat.chat_type != "private" or not chat.account_id:
            return chat.env["res.users"]
        return chat.account_id._acting_user("internal")

    def _router(self):
        return self.env["telegram.router"]

    # -- messages -------------------------------------------------------------

    @staticmethod
    def _clear_keyboard(bot, chat, callback_query) -> None:
        """Take the buttons off the message whose button was pressed."""
        message_id = (callback_query.get("message") or {}).get("message_id")
        if message_id:
            bot.edit_message_reply_markup(chat.chat_id, message_id, reply_markup=None)

    @staticmethod
    def _body_of(message):
        """A message's text or caption as Odoo HTML."""
        text = message.get("text") or message.get("caption") or ""
        if not text:
            return Markup()
        return Markup("<br>").join(escape(line) for line in text.split("\n"))

    @staticmethod
    def _files_of(message, kinds=("photo", "document")):
        """`[(file_id, name)]` of the files of `kinds` a message carries: the
        largest size of a photo, a file under the name it was sent with."""
        files = []
        for kind, default_name in _FILES:
            item = message.get(kind) if kind in kinds else None
            if not item:
                continue
            if kind == "photo":
                item = item[-1]
            files.append((item["file_id"], item.get("file_name") or default_name))
        return files

    def _download(self, bot, message, kinds=("photo", "document")):
        """`[(name, bytes)]` of the files of `kinds` a message carries; a file
        Telegram would not hand over is left out."""
        attachments = []
        for file_id, name in self._files_of(message, kinds):
            downloaded = bot.get_file(file_id)
            if downloaded:
                attachments.append((name, downloaded["content"]))
        return attachments
