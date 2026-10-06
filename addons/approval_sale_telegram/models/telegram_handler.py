from odoo import models

from odoo.addons.telegram.tools import format as tg

_CALLBACK_PREFIX = "sc:"


class TelegramHandlerSaleConfirm(models.AbstractModel):
    _name = "telegram.handler.sale.confirm"
    _inherit = "mixin.telegram.handler"
    _description = "Telegram: Sale Order Confirmation"

    def _telegram_callback_prefixes(self):
        return (_CALLBACK_PREFIX,)

    def _on_callback(self, bot, chat, callback_query, partner, internal_user):
        data = callback_query.get("data") or ""
        if not data.startswith(_CALLBACK_PREFIX):
            return False
        bot.answer_callback_query(callback_query.get("id"))
        self._handle_confirm_callback(bot, chat, callback_query, internal_user, data)
        return True

    def _handle_confirm_callback(self, bot, chat, callback_query, internal_user, data):
        env = self._tr(bot, chat)
        parts = data.split(":")
        if len(parts) != 3 or parts[1] != "c" or not parts[2].isdigit():
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
        error = env["telegram.sale.confirm.notifier"].confirm(order, internal_user, bot)
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
