from typing import TYPE_CHECKING, Any, Literal

from odoo import models

from odoo.addons.telegram.tools import format as tg

if TYPE_CHECKING:
    from odoo.addons.approval.models.res_users import ResUsers
    from odoo.addons.base.models.res_partner import ResPartner
    from odoo.addons.telegram.models.telegram_bot import TelegramBot
    from odoo.addons.telegram.models.telegram_chat import TelegramChat

_CALLBACK_PREFIX = "sc:"


class TelegramHandlerSaleConfirm(models.AbstractModel):
    _name = "telegram.handler.sale.confirm"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Sale Order Confirmation"

    def _telegram_callback_prefixes(self) -> tuple[str, ...]:
        return (_CALLBACK_PREFIX,)

    def _on_callback(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        callback_query: dict[str, Any],
        partner: ResPartner,
        internal_user: ResUsers | Literal[False],
    ) -> bool:
        data = callback_query.get("data") or ""
        if not data.startswith(_CALLBACK_PREFIX):
            return False
        bot.answer_callback_query(callback_query.get("id"))
        self._handle_confirm_callback(bot, chat, callback_query, internal_user, data)
        return True

    def _handle_confirm_callback(
        self,
        bot: TelegramBot,
        chat: TelegramChat,
        callback_query: dict[str, Any],
        internal_user: ResUsers | Literal[False],
        data: str,
    ) -> None:
        env = self._tr(bot, chat)
        parts = data.split(":")
        if len(parts) != 3 or parts[1] != "c" or not parts[2].isdecimal():
            return
        if not internal_user:
            bot.send_message(
                chat.chat_id,
                env._(
                    "To confirm orders your Odoo account must be linked to this "
                    "chat. Ask IT to link your Telegram user."
                ),
            )
            return
        order = env["sale.order"].sudo().browse(int(parts[2])).exists()
        if not order:
            bot.send_message(chat.chat_id, env._("This order no longer exists."))
            return
        error = env["telegram.sale.confirm.notifier"]._confirm(
            order, internal_user, bot
        )
        if error:
            bot.send_message(
                chat.chat_id,
                env._("Could not confirm %(order)s: %(error)s")
                % {"order": tg.escape(order.name), "error": tg.escape(error)},
            )
            return
        self._clear_keyboard(bot, chat, callback_query)
        bot.send_message(
            chat.chat_id,
            env._("✅ You confirmed order %(order)s.")
            % {"order": tg.escape(order.name)},
        )
