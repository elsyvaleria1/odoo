from odoo.fields import Domain
from odoo.http import request

from odoo.addons.mail.controllers.discuss.messaging_menu import (
    DiscussMessagingMenuController,
)

LIVECHAT_CHANNEL_FILTER_PREFIX = "livechat_channel_"


class LivechatMessagingMenuController(DiscussMessagingMenuController):
    @classmethod
    def _get_menu_tab_domain(cls, tab_id: str) -> Domain:
        if tab_id != "livechat":
            return super()._get_menu_tab_domain(tab_id)
        visible_domain = Domain("self_member_id.is_pinned", "=", True)
        if request.env.user.has_access_livechat:
            visible_domain |= Domain("livechat_status", "=", "need_help")
        return Domain("channel_type", "=", "livechat") & visible_domain

    @classmethod
    def _get_menu_tab_filter_domain(cls, tab_id: str, filter_id: str) -> Domain:
        match (tab_id, filter_id):
            case ("livechat", "livechat_unread"):
                return Domain("self_member_id.is_unread", "=", True)
            case ("livechat", "livechat_need_help"):
                return Domain("livechat_status", "=", "need_help")
        if tab_id == "livechat" and (
            livechat_channel_id := cls._parse_livechat_channel_filter(filter_id)
        ):
            return Domain("livechat_channel_id", "=", livechat_channel_id)
        return super()._get_menu_tab_filter_domain(tab_id, filter_id)

    @staticmethod
    def _parse_livechat_channel_filter(filter_id: str) -> int | None:
        suffix = filter_id.removeprefix(LIVECHAT_CHANNEL_FILTER_PREFIX)
        if suffix == filter_id or not (suffix.isascii() and suffix.isdigit()):
            return None
        return int(suffix) or None
