from odoo import http
from odoo.http import request

from ..tools.telegram_client import TelegramClient


class TelegramController(http.Controller):
    """The webhook: admission, then telegram.router. What an update does is
    the router's and its handlers', which live in the database's registry."""

    @http.route(
        "/telegram/webhook/<string:token>",
        type="http",
        auth="receiver",
        receiver="telegram.bot:_receiver_for_webhook",
        receiver_event="update",
        receiver_refusal="telegram.bot:_prepare_webhook_refusal_response",
        methods=["POST"],
        csrf=False,  # auth="receiver": the bot's webhook gate checks Telegram's secret token
        save_session=False,
        typed=True,
    )
    def webhook(self, token: str, **kwargs):
        admission = request.admission
        bot = admission.subject
        data = admission.json()
        admission.retag(
            next(
                (key for key in TelegramClient.ALLOWED_UPDATES if key in data),
                "update",
            )
        )
        try:
            bot.env["telegram.router"]._handle_update(bot, data)
        except Exception as error:
            admission.settle(f"{type(error).__name__}: {error}")
            raise
        admission.settle()
        return request.prepare_response("OK", status=200)
