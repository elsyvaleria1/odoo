from werkzeug.exceptions import NotFound

from odoo import http

from odoo.addons.mail.controllers.thread import ThreadController
from odoo.addons.mail.tools.discuss import add_guest_to_context


class AIController(ThreadController):
    # auth=public to allow visitors to interact with ai agents through livechat
    @http.route(["/ai/generate_response"], type="jsonrpc", auth="public")
    @add_guest_to_context
    def generate_response(
        self,
        mail_message_id,
        channel_id,
        current_view_info=None,
        ai_session_identifier=None,
    ):
        channel = self._get_ai_channel_from_id(channel_id)
        if not channel:
            raise NotFound
        message = self._get_message_with_access(mail_message_id)
        if message:
            channel.with_context(
                current_view_info=current_view_info,
                ai_session_identifier=ai_session_identifier,
            )._ai_answer(message)

    @http.route("/ai/close_ai_chat", methods=["POST"], type="jsonrpc", auth="public")
    @add_guest_to_context
    def close_ai_chat(self, channel_id):
        channel = self._get_ai_channel_from_id(channel_id)
        if channel and self._is_unlink_on_close_required(channel):
            channel.sudo().unlink()

    def _is_unlink_on_close_required(self, channel) -> bool:
        return bool(channel.is_member)

    def _get_ai_channel_from_id(self, channel_id):
        channel = self.env["discuss.channel"].search([("id", "=", channel_id)])
        if channel._ai_answering().ai_agent_id:
            return channel
        return self.env["discuss.channel"]
