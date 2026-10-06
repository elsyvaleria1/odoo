from typing import Any

from werkzeug.exceptions import BadRequest

from odoo.fields import Domain
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.mail.controllers.messaging_menu import MessagingMenuController
from odoo.addons.mail.tools.discuss import Store

_debug = DebugLog(__name__)

MOST_POPULAR_CHANNELS_LIMIT = 3


class DiscussMessagingMenuController(MessagingMenuController):
    @classmethod
    def _get_menu_tab_domain(cls, tab_id: str) -> Domain:
        match tab_id:
            case "notification":
                return super()._get_menu_tab_domain(tab_id) & Domain(
                    "model", "!=", "discuss.channel"
                )
            case "chat":
                return (
                    Domain(
                        [
                            ("channel_type", "in", ["chat", "group"]),
                            ("self_member_id.is_pinned", "=", True),
                        ]
                    )
                    & ~request.env["discuss.channel"]._get_meeting_domain()
                )
            case "channel":
                channel_domain = Domain("self_member_id.is_pinned", "=", True)
                if request.env.user._is_internal():
                    channel_domain |= Domain("message_needaction", "=", True)
                return Domain("channel_type", "=", "channel") & channel_domain
            case "meeting":
                return (
                    Domain("channel_type", "=", "group")
                    & Domain("self_member_id.is_pinned", "=", True)
                    & request.env["discuss.channel"]._get_meeting_domain()
                )
            case _:
                return super()._get_menu_tab_domain(tab_id)

    @classmethod
    def _get_menu_tab_filter_domain(cls, tab_id: str, filter_id: str) -> Domain:
        match (tab_id, filter_id):
            case (
                ("chat", "chat_unread")
                | ("channel", "channel_unread")
                | ("meeting", "meeting_unread")
            ):
                return Domain("self_member_id.is_unread", "=", True)
            case ("chat", "chat_group"):
                return Domain("channel_type", "=", "group")
            case ("channel", "channel_thread") | ("meeting", "meeting_thread"):
                return Domain("parent_channel_id", "!=", False)
            case ("meeting", "meeting_today"):
                return request.env["discuss.channel"]._get_meeting_today_domain()
        return super()._get_menu_tab_filter_domain(tab_id, filter_id)

    @classmethod
    def _get_menu_tab_order(cls, tab_id: str) -> str:
        if tab_id == "meeting":
            return "is_favorite DESC, is_meeting_over, last_interest_dt DESC, id DESC"
        return "is_favorite DESC, last_interest_dt DESC, id DESC"

    @classmethod
    def _get_menu_important_channels_domain(cls) -> Domain:
        domain = Domain(
            "channel_member_ids",
            "any",
            [
                ("is_self", "=", True),
                ("is_pinned", "=", True),
                ("is_unread", "=", True),
                ("mute_until_dt", "=", False),
            ],
        )
        if request.env.user._is_internal():
            domain |= Domain("message_needaction", "=", True)
        return Domain("active", "=", True) & domain

    @classmethod
    def _process_request_for_all(cls, store: Store, name: str, params: Any) -> None:
        super()._process_request_for_all(store, name, params)
        if name == "/mail/messaging_menu/initialize_counters":
            filter_id_by_tab_id = cls._get_filter_id_by_tab_id(
                params, "discuss.channel"
            )
            if not filter_id_by_tab_id:
                return
            domain_by_tab_id = cls._get_menu_counter_domain_by_tab_id(
                "discuss.channel", filter_id_by_tab_id
            )
            channels = request.env["discuss.channel"].search(
                cls._get_menu_important_channels_domain()
            )
            cls._add_menu_tab_counters(store, channels, domain_by_tab_id)
            cls._add_menu_tab_presence(
                store, "discuss.channel", params, filter_id_by_tab_id
            )
        if name == "/mail/messaging_menu/discuss.channel/load_more":
            cls._messaging_menu_channel_load_more(store, params)
        if name == "/mail/messaging_menu/get_most_popular_channels":
            groups = request.env["discuss.channel.member"]._read_group(
                [("channel_id.channel_type", "=", "channel")],
                ["channel_id"],
                order="__count DESC, channel_id DESC",
                limit=MOST_POPULAR_CHANNELS_LIMIT,
            )
            channels = (
                request.env["discuss.channel"]
                .browse([channel.id for (channel,) in groups])
                ._filtered_access("read")
            )
            request.update_context(channels=request.env.context["channels"] | channels)
            store.add_global_values(most_popular_channels=Store.Many(channels, []))

    @classmethod
    def _messaging_menu_channel_load_more(cls, store: Store, params: Any) -> None:
        if not isinstance(params, dict):
            raise BadRequest("Invalid messaging menu load more request")
        limit = request.env["mail.message"]._clamp_fetch_limit(params.get("limit"))
        domain = cls._get_menu_load_more_domain("discuss.channel", params)
        search_term = params.get("search_term")
        if search_term and isinstance(search_term, str):
            domain &= Domain("name", "ilike", search_term)
        channels = request.env["discuss.channel"].search(
            domain, limit=limit, order=cls._get_menu_tab_order(params.get("tab_id"))
        )
        _debug.logic(
            "messaging_menu_load_more",
            model="discuss.channel",
            tab=params.get("tab_id"),
            fetched=len(channels),
            limit=limit,
        )
        request.update_context(
            channels=request.env.context["channels"] | channels,
            add_channels_last_message=True,
        )
        store.resolve_data_request(is_fully_loaded=len(channels) < limit)
