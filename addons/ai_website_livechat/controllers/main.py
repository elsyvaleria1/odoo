from odoo import http
from odoo.http import request

from odoo.addons.mail.tools.discuss import Store, add_guest_to_context


class AIWebsiteLivechatController(http.Controller):
    @http.route(
        "/ai_website_livechat/create_chat_channel",
        methods=["POST"],
        type="jsonrpc",
        auth="public",
    )
    @add_guest_to_context
    def create_chat_channel_with_ai_agent(self, ai_agent_id):
        ai_agent = self.env["ai.agent"].sudo().search([("id", "=", ai_agent_id)])
        if not ai_agent or not ai_agent._is_user_access_allowed():
            return None

        store = Store()
        guest = request.env["mail.guest"]
        if request.env.user._is_public():
            guest = guest.sudo()._get_or_create_guest(
                guest_name=self._get_guest_name(),
                country_code=request.geoip.country_code,
                timezone=request.env["mail.guest"]._get_timezone_from_request(request),
            )
            ai_agent = ai_agent.with_context(guest=guest)
            request.update_context(guest=guest)
        if guest:
            store.add_global_values(guest_token=guest.sudo()._format_auth_cookie())
        active_chat_channel = ai_agent._get_ai_chat_channel()
        ai_agent._lock_ai_chat_creation()
        ai_agent._check_no_ai_chat_committed_unseen(active_chat_channel)
        if active_chat_channel:
            active_chat_channel.sudo().unlink()
        channel = ai_agent._create_ai_chat_channel()
        request.env["res.users"]._init_store_data(store)
        store.add(channel)
        return {"channel_id": channel.id, "store_data": store.get_result()}

    def _get_guest_name(self):
        return request.env._("Visitor")

    @http.route(
        "/ai_website_livechat/is_livechat_operator_available",
        methods=["POST"],
        type="jsonrpc",
        auth="public",
    )
    @add_guest_to_context
    def is_livechat_operator_available(self, livechat_channel_id) -> bool:
        country = request.env["res.country"]
        if not request.env.user._is_public():
            country = request.env.user.country_id
        elif request.geoip.country_code:
            country = request.env["res.country"].search(
                [("code", "=", request.geoip.country_code)], limit=1
            )
        livechat_channel = (
            request.env["im_livechat.channel"]
            .sudo()
            .search([("id", "=", livechat_channel_id)])
        )
        if not livechat_channel:
            return False
        operator = livechat_channel._get_operator(
            country_id=country.id, lang=request.cookies.get("frontend_lang")
        )
        operator -= self.env.user
        return bool(operator)
