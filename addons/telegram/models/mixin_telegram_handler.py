from datetime import timedelta
from typing import TYPE_CHECKING, Any, Literal

from markupsafe import Markup, escape

from odoo import models

from ..tools import format as tg
from ..tools.authority import keeping
from ..tools.dispatch import translation_env

if TYPE_CHECKING:
    from odoo.api import Environment

    from ..tools.dispatch import TelegramCommand
    from .telegram_account import TelegramAccount
    from .telegram_binding import TelegramBinding
    from .telegram_bot import TelegramBot
    from .telegram_business_connection import TelegramBusinessConnection
    from .telegram_chat import TelegramChat
    from .telegram_link_token import TelegramLinkToken
    from .telegram_message import TelegramMessage
    from .telegram_router import TelegramRouter
    from odoo.addons.base.models.res_company import ResCompany
    from odoo.addons.base.models.res_partner import ResPartner
    from odoo.addons.base.models.res_users import ResUsers

_FILES = (
    ("photo", "photo.jpg"),
    ("document", "document"),
    ("voice", "voice.ogg"),
    ("audio", "audio"),
    ("video", "video.mp4"),
)


class MixinTelegramHandler(models.AbstractModel):
    _name = "mixin.telegram.handler"
    _description = "Telegram Handler"

    _telegram_intake_priority = 100
    _telegram_flow_ttl = timedelta(hours=1)

    def _telegram_commands(self) -> dict[str, TelegramCommand]:
        return {}

    def _telegram_callback_prefixes(self) -> tuple[str, ...]:
        return ()

    def _telegram_intakes(self) -> frozenset[str]:
        return frozenset()

    def _feature_enabled(self, bot: TelegramBot) -> bool:
        commands = self._telegram_commands()
        if not commands:
            return True
        linked = set(bot.command_ids.mapped("name"))
        return bool(linked & set(commands))

    def _telegram_flow_label(self, bot: TelegramBot, chat: TelegramChat) -> str:
        return self._tr(bot, chat)._("an operation")

    def _on_flow_cancelled(self, bot: TelegramBot, chat: TelegramChat) -> None:
        pass

    def _owns_flow(self, chat: TelegramChat) -> bool:
        return chat._flow_is_open() and chat.flow_owner == self._name

    def _flow_step(self, chat: TelegramChat) -> str | None:
        return (chat.flow_step or None) if self._owns_flow(chat) else None

    def _flow_data(self, chat: TelegramChat) -> dict[str, Any]:
        return dict(chat.flow_data or {}) if self._owns_flow(chat) else {}

    def _flow_start(
        self, chat: TelegramChat, step: str, data: dict[str, Any] | None = None
    ) -> None:
        chat._flow_start(self._name, step, data)

    def _flow_end(self, chat: TelegramChat) -> None:
        if chat.flow_owner == self._name:
            chat._flow_end()

    def _claims_message(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        message: dict[str, Any],
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        return False

    def _accepts_idle(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        kind: str,
        message: dict[str, Any],
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        return kind in self._telegram_intakes()

    def _telegram_intake_command(
        self, bot: TelegramBot, chat: TelegramChat, kind: str
    ) -> str | None:
        return None

    def _telegram_intake_label(
        self, bot: TelegramBot, chat: TelegramChat, kind: str
    ) -> str:
        name = (
            self.env["ir.model"]
            ._get(self._name)
            .with_context(lang=self._tr(bot, chat).lang)
        )
        return (name.name or self._description).removeprefix("Telegram: ")

    def _on_unhandled_message(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        message: dict[str, Any],
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        return False

    def _on_message(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        message: dict[str, Any],
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        return False

    def _on_edited_message(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        message: dict[str, Any],
        ledger: TelegramMessage,
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        return False

    def _on_group_link(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        link: TelegramLinkToken,
        account: TelegramAccount,
    ) -> bool:
        return False

    def _on_channel_link(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        link: TelegramLinkToken,
        account: TelegramAccount,
    ) -> bool:
        return False

    def _on_forum_topic(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        thread_uid: str,
        event: str,
        data: dict[str, Any],
    ) -> bool:
        return False

    def _on_reaction(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        ledger: TelegramMessage,
        account: TelegramAccount,
        *,
        added: set[str],
        removed: set[str],
    ) -> bool:
        return False

    def _on_chat_migrated(
        self, bot: TelegramBot, group: TelegramChat, supergroup: TelegramChat
    ) -> None:
        pass

    def _on_bot_membership(
        self, bot: TelegramBot, chat: TelegramChat, status: str
    ) -> None:
        pass

    def _on_account_bound(
        self, bot: TelegramBot, chat: TelegramChat, binding: TelegramBinding
    ) -> None:
        pass

    def _on_phone_verified(
        self, bot: TelegramBot, chat: TelegramChat, account: TelegramAccount
    ) -> None:
        pass

    def _on_business_message(
        self,
        bot: TelegramBot,
        connection: TelegramBusinessConnection,
        chat: TelegramChat,
        message: dict[str, Any],
        from_owner: bool,
        edited: bool,
    ) -> bool:
        return False

    def _on_business_deleted(
        self,
        bot: TelegramBot,
        connection: TelegramBusinessConnection,
        chat: TelegramChat,
        ledgers: TelegramMessage,
    ) -> bool:
        return False

    def _on_callback(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        callback_query: dict[str, Any],
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        return False

    def _command_allowed(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        command: str,
        partner: ResPartner | Literal[False],
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        return True

    def _command_companies(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        command: str,
        partner: ResPartner | Literal[False],
        internal_user: ResUsers | Literal[False],
    ) -> ResCompany:
        if internal_user:
            return bot._served_companies(internal_user)
        return keeping(bot).company_ids.with_env(bot.env)

    def _explain_command_refusal(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        command: str,
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> None:
        bot.send_message(
            chat.chat_id,
            self._tr(bot, chat)._(
                "You don't have permission to use the command %(command)s."
            )
            % {"command": tg.code(command)},
        )

    def _offers_command(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        command: str,
        partner: ResPartner | Literal[False],
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        spec = self._telegram_commands().get(command)
        router = self._router()
        return bool(
            spec
            and router._is_command_enabled(bot, self, command, spec)
            and router._command_permitted(
                bot, chat, self, command, spec, partner, internal_user
            )
        )

    def _get_help_sections(
        self,
        bot: TelegramBot,
        partner: ResPartner | Literal[False],
        internal_user: ResUsers | Literal[False],
        chat: TelegramChat | None = None,
    ) -> list[tuple[str, list[str]]]:
        return []

    def _tr(self, bot: TelegramBot, chat: TelegramChat | None = None) -> Environment:
        return translation_env(bot, chat)

    @staticmethod
    def _chat_internal_user(chat: TelegramChat) -> ResUsers:
        if chat.chat_type != "private" or not chat.account_id:
            return chat.env["res.users"]
        return chat.account_id._acting_user("internal")

    def _router(self) -> TelegramRouter:
        return self.env["telegram.router"]

    @staticmethod
    def _clear_keyboard(
        bot: TelegramBot, chat: TelegramChat, callback_query: dict[str, Any]
    ) -> None:
        message_id = (callback_query.get("message") or {}).get("message_id")
        if message_id:
            bot.edit_message_reply_markup(chat.chat_id, message_id, reply_markup=None)

    @staticmethod
    def _body_of(message: dict[str, Any]) -> Markup:
        text = message.get("text") or message.get("caption") or ""
        if not text:
            return Markup()
        return Markup("<br>").join(escape(line) for line in text.split("\n"))

    @staticmethod
    def _files_of(
        message: dict[str, Any], kinds: tuple[str, ...] = ("photo", "document")
    ) -> list[tuple[str, str]]:
        files = []
        for kind, default_name in _FILES:
            item = message.get(kind) if kind in kinds else None
            if not item:
                continue
            if kind == "photo":
                item = item[-1]
            files.append((item["file_id"], item.get("file_name") or default_name))
        return files

    def _download(
        self,
        bot: TelegramBot,
        message: dict[str, Any],
        kinds: tuple[str, ...] = ("photo", "document"),
    ) -> list[tuple[str, bytes]]:
        attachments = []
        for file_id, name in self._files_of(message, kinds):
            downloaded = bot.get_file(file_id)
            if downloaded:
                attachments.append((name, downloaded["content"]))
        return attachments
