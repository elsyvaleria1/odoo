from odoo.fields import Domain

from odoo.addons.mail.controllers.discuss.messaging_menu import (
    DiscussMessagingMenuController,
)


class TwilioMessagingMenuController(DiscussMessagingMenuController):
    @classmethod
    def _get_menu_tab_domain(cls, tab_id: str) -> Domain:
        if tab_id != "sms":
            return super()._get_menu_tab_domain(tab_id)
        return Domain([("channel_type", "=", "sms"), ("is_member", "=", True)])

    @classmethod
    def _get_menu_tab_filter_domain(cls, tab_id: str, filter_id: str) -> Domain:
        if (tab_id, filter_id) == ("sms", "sms_unread"):
            return Domain("self_member_id.is_unread", "=", True)
        return super()._get_menu_tab_filter_domain(tab_id, filter_id)
