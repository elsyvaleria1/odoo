import logging

from odoo import models

from ..tools import format as tg
from ..tools.authority import operating
from ..tools.dispatch import TelegramCommand, log_command_execution, translation_env

_logger = logging.getLogger(__name__)


class TelegramHandlerBase(models.AbstractModel):
    """What every bot answers: the welcome, help, who-am-I, connecting and
    disconnecting, cancelling whatever flow is open, and a shared contact
    card."""

    _name = "telegram.handler.base"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: General Commands"

    def _telegram_commands(self) -> dict:
        return {
            "/start": TelegramCommand(
                "_handle_start_command", "unlinked", builtin=True
            ),
            "/ayuda": TelegramCommand("_handle_help_command", "unlinked", builtin=True),
            "/quiensoy": TelegramCommand(
                "_handle_whoami_command", "partner", builtin=True
            ),
            "/desconectar": TelegramCommand(
                "_handle_disconnect_command", "partner", builtin=True
            ),
            # unlinked: the least a command opening a flow asks (/subirfactura)
            "/cancelar": TelegramCommand(
                "_handle_cancel_command", "unlinked", builtin=True
            ),
        }

    def _feature_enabled(self, bot):
        return True

    def _telegram_intakes(self):
        return frozenset({"contact"})

    def _on_message(self, bot, chat, message, partner, internal_user):
        if not message.get("contact"):
            return False
        self._handle_shared_contact(bot, chat, message, partner, internal_user)
        return True

    @log_command_execution
    def _handle_start_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr_env = translation_env(bot, chat)
        if args and chat.chat_type == "private" and chat.account_id:
            self._bind_from_start(bot, chat, args[0])
            return
        welcome_message = tr_env._(
            "Welcome to %(bot_name)s!\nType /ayuda to see what I can do."
        ) % {"bot_name": tg.bold(bot.name)}
        bot.send_message(chat.chat_id, welcome_message)

    def _bind_from_start(self, bot, chat, token) -> None:
        tr_env = translation_env(bot, chat)
        account = chat.account_id
        link = bot.env["telegram.link.token"]._consume(bot, token, account)
        if not link:
            bot.send_message(
                chat.chat_id,
                tr_env._(
                    "This link is expired or was already used. Open Odoo and "
                    "connect Telegram again to get a new one."
                ),
                parse_mode=None,
            )
            return
        binding = account._bind(
            link.partner_id, user=link.user_id or None, method=link.method
        )
        _logger.info(
            "Telegram account %s bound to partner %s (user %s) by %s link %s",
            account.id,
            binding.partner_id.id,
            binding.user_id.id or "-",
            link.method,
            link.id,
        )
        tr_env = translation_env(bot, chat.with_env(bot.env))
        bot.send_message(
            chat.chat_id,
            tr_env._(
                "Connected: this Telegram account is %(name)s in Odoo. "
                "Send /desconectar to undo it."
            )
            % {"name": binding.partner_id.name},
            parse_mode=None,
        )

    @log_command_execution
    def _handle_disconnect_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr_env = translation_env(bot, chat)
        binding = operating(chat.account_id).binding_id
        if not binding:
            bot.send_message(
                chat.chat_id,
                tr_env._("This Telegram account is not connected to Odoo."),
                parse_mode=None,
            )
            return
        binding._revoke("user")
        bot.send_message(
            chat.chat_id,
            tr_env._(
                "Disconnected. This Telegram account no longer acts as anyone in Odoo."
            ),
            parse_mode=None,
        )

    @log_command_execution
    def _handle_cancel_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr_env = translation_env(bot, chat)
        owner = self.env["telegram.router"]._flow_owner(chat)
        label = owner._telegram_flow_label(bot, chat) if owner is not None else None
        self.env["telegram.router"]._cancel_flow(bot, chat)
        if label is None:
            text = tr_env._("You have nothing in progress to cancel.")
        else:
            text = tr_env._("Done, I cancelled %(flow)s.") % {"flow": label}
        bot.send_message(chat.chat_id, text, parse_mode=None)

    def _get_help_sections(self, bot, partner, internal_user, chat=None):
        tr_env = translation_env(bot, chat)
        general_cmds = []
        if partner:
            general_cmds.append(tr_env._("/quiensoy - Verify your identity in Odoo."))
            general_cmds.append(
                tr_env._("/desconectar - Disconnect this Telegram account from Odoo.")
            )
        general_cmds.append(tr_env._("/cancelar - Cancel what you have in progress."))
        general_cmds.append(tr_env._("/ayuda - Show this help message."))

        return [(tr_env._("General Commands"), general_cmds)]

    @log_command_execution
    def _handle_help_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        sections = self.env["telegram.router"]._help_sections(
            bot, partner, internal_user, chat=chat
        )

        message_parts = []
        for title, commands in sections:
            if commands:
                message_parts.append(tg.bold(f"📋 {title}:"))
                message_parts.extend(commands)
                message_parts.append("")

        if message_parts and not message_parts[-1]:
            message_parts.pop()

        bot.send_message(chat.chat_id, "\n".join(message_parts))

    @log_command_execution
    def _handle_whoami_command(
        self, bot, chat, args, partner=False, internal_user=False
    ) -> None:
        tr_env = translation_env(bot, chat)

        if internal_user:
            user_message = tr_env._(
                "You are operating as the Odoo user:\n- %(bold_name)s %(name)s\n- "
                "%(bold_email)s %(email)s"
            ) % {
                "bold_name": tg.bold(tr_env._("Name:")),
                "name": tg.escape(internal_user.name),
                "bold_email": tg.bold(tr_env._("Email:")),
                "email": tg.escape(internal_user.login),
            }
        elif partner:
            user_message = tr_env._(
                "This Telegram chat is linked to the Odoo contact:\n- %(bold_name)s "
                "%(name)s"
            ) % {
                "bold_name": tg.bold(tr_env._("Name:")),
                "name": tg.escape(partner.name),
            }
        else:
            user_message = tr_env._("This chat is not linked to any Odoo contact.")
        expires_at = operating(chat.account_id).binding_id.expires_at
        if (partner or internal_user) and expires_at:
            user_message += "\n\n" + tr_env._(
                "Confirm this connection before %(date)s: in Odoo, open My "
                "Preferences and press Connect Telegram."
            ) % {"date": tg.escape(expires_at.date().isoformat())}
        bot.send_message(chat.chat_id, user_message)

    def _handle_shared_contact(
        self, bot, chat, message, partner, internal_user
    ) -> None:
        tr_env = translation_env(bot, chat)
        if partner:
            bot.send_message(
                chat.chat_id,
                tr_env._("Your chat is already linked to: %(partner_name)s")
                % {"partner_name": tg.bold(partner.name)},
                reply_markup={"remove_keyboard": True},
            )
            return

        _logger.info(
            "Received shared contact for chat %s - manual linking required",
            chat.id,
        )
        bot.send_message(
            chat.chat_id,
            tr_env._(
                "To connect this chat to Odoo, open My Preferences in Odoo and "
                "press Connect Telegram, or ask an administrator for an "
                "invitation."
            ),
            reply_markup={"remove_keyboard": True},
        )
