from odoo import http
from odoo.http import request

from ..tools.authority import operating


class TelegramConnectController(http.Controller):
    @http.route(
        "/telegram/connect/<int:bot_id>",
        type="http",
        auth="user",
        methods=["GET"],
    )
    def connect(self, bot_id, **kwargs):
        bot = operating(request.env["telegram.bot"]).browse(bot_id).exists()
        if not bot or not bot.bot_username:
            return request.not_found()
        token = request.env["telegram.link.token"]._issue_for_session(bot)
        return request.redirect(bot._deep_link(token), local=False)
