from datetime import timedelta

from markupsafe import Markup, escape

from odoo import models

from ..tools import format as tg
from ..tools.authority import keeping
from ..tools.dispatch import translation_env

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

      - its commands (`_telegram_commands`), with who may run them: the
        tier, the Odoo groups and access, then `_command_allowed`, which
        only answers -- `_explain_command_refusal` tells the person;
      - the callback-data prefixes of its buttons: two handlers claiming one
        prefix fail the registry load;
      - what its multi-step flows are called (`_telegram_flow_label`): a
        flow it opens on a chat is its own, gets that chat's free text and
        nobody else's, and ends by its own step, by expiring, or by /cancelar;
      - the message kinds it takes from an idle chat (text, voice, photo,
        document, contact, location): when several take a person's message,
        the one the bot names for its kind does, else the bot asks the person
        which (`_telegram_intake_label`); one standing for a command
        (`_telegram_intake_command`) follows that command's permissions and
        company.

    Extending a handler is Odoo inheritance: `_inherit` it and call super().
    """

    _name = "mixin.telegram.handler"
    _description = "Telegram Handler"

    _telegram_intake_priority = 100
    _telegram_flow_ttl = timedelta(hours=1)

    def _telegram_commands(self) -> dict:
        return {}

    def _telegram_callback_prefixes(self):
        return ()

    def _telegram_intakes(self):
        return frozenset()

    def _feature_enabled(self, bot):
        commands = self._telegram_commands()
        if not commands:
            return True
        linked = set(bot.command_ids.mapped("name"))
        return bool(linked & set(commands))


    def _telegram_flow_label(self, bot, chat):
        return self._tr(bot, chat)._("an operation")

    def _on_flow_cancelled(self, bot, chat):
        pass

    def _owns_flow(self, chat):
        return chat._flow_is_open() and chat.flow_owner == self._name

    def _flow_step(self, chat):
        return chat.flow_step if self._owns_flow(chat) else False

    def _flow_data(self, chat):
        return dict(chat.flow_data or {}) if self._owns_flow(chat) else {}

    def _flow_start(self, chat, step, data=None) -> None:
        chat._flow_start(self._name, step, data)

    def _flow_end(self, chat) -> None:
        if chat.flow_owner == self._name:
            chat._flow_end()

    def _claims_message(self, bot, chat, message, partner, internal_user) -> bool:
        return False

    def _accepts_idle(self, bot, chat, kind, message, partner, internal_user):
        return kind in self._telegram_intakes()

    def _telegram_intake_command(self, bot, chat, kind) -> str | None:
        return None

    def _telegram_intake_label(self, bot, chat, kind) -> str:
        name = (
            self.env["ir.model"]
            ._get(self._name)
            .with_context(lang=self._tr(bot, chat).lang)
        )
        return (name.name or self._description).removeprefix("Telegram: ")

    def _on_unhandled_message(self, bot, chat, message, partner, internal_user):
        return False

    def _on_message(self, bot, chat, message, partner, internal_user):
        return False

    def _on_edited_message(
        self, bot, chat, message, ledger, partner, internal_user
    ) -> bool:
        return False

    def _on_group_link(self, bot, chat, link, account) -> bool:
        return False

    def _on_channel_link(self, bot, chat, link, account) -> bool:
        return False

    def _on_forum_topic(self, bot, chat, thread_uid, event, data) -> bool:
        return False

    def _on_reaction(self, bot, chat, ledger, account, *, added, removed) -> bool:
        return False

    def _on_chat_migrated(self, bot, group, supergroup):
        pass

    def _on_bot_membership(self, bot, chat, status):
        pass

    def _on_account_bound(self, bot, chat, binding) -> None:
        pass

    def _on_phone_verified(self, bot, chat, account) -> None:
        pass

    def _on_business_message(
        self, bot, connection, chat, message, from_owner, edited
    ) -> bool:
        return False

    def _on_business_deleted(self, bot, connection, chat, ledgers) -> bool:
        return False

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        return False

    def _command_allowed(self, bot, chat, command, partner, internal_user) -> bool:
        return True

    def _command_companies(self, bot, chat, command, partner, internal_user):
        if internal_user:
            return bot._served_companies(internal_user)
        return keeping(bot).company_ids.with_env(bot.env)

    def _explain_command_refusal(
        self, bot, chat, command, partner, internal_user
    ) -> None:
        bot.send_message(
            chat.chat_id,
            self._tr(bot, chat)._(
                "You don't have permission to use the command %(command)s."
            )
            % {"command": tg.code(command)},
        )

    def _offers_command(self, bot, chat, command, partner, internal_user) -> bool:
        spec = self._telegram_commands().get(command)
        router = self._router()
        return bool(
            spec
            and router._is_command_enabled(bot, self, command, spec)
            and router._command_permitted(
                bot, chat, self, command, spec, partner, internal_user
            )
        )

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        return []

    def _tr(self, bot, chat=None):
        return translation_env(bot, chat)

    @staticmethod
    def _chat_internal_user(chat):
        if chat.chat_type != "private" or not chat.account_id:
            return chat.env["res.users"]
        return chat.account_id._acting_user("internal")

    def _router(self):
        return self.env["telegram.router"]


    @staticmethod
    def _clear_keyboard(bot, chat, callback_query) -> None:
        message_id = (callback_query.get("message") or {}).get("message_id")
        if message_id:
            bot.edit_message_reply_markup(chat.chat_id, message_id, reply_markup=None)

    @staticmethod
    def _body_of(message):
        text = message.get("text") or message.get("caption") or ""
        if not text:
            return Markup()
        return Markup("<br>").join(escape(line) for line in text.split("\n"))

    @staticmethod
    def _files_of(message, kinds=("photo", "document")):
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
        attachments = []
        for file_id, name in self._files_of(message, kinds):
            downloaded = bot.get_file(file_id)
            if downloaded:
                attachments.append((name, downloaded["content"]))
        return attachments
