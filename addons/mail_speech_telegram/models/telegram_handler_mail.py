from odoo import models


class TelegramHandlerMail(models.AbstractModel):
    _inherit = "telegram.handler.mail"

    def _voice_text(self, bot, chat, message, user):
        return bot._hear_message(chat, message, language=(user.lang or "es")[:2]).text
