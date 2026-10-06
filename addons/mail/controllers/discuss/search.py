from odoo import http
from odoo.fields import Domain
from odoo.http import request
from odoo.libs.debug_log import DebugLog

from odoo.addons.mail.controllers.discuss.messaging_menu import (
    DiscussMessagingMenuController,
)
from odoo.addons.mail.controllers.utils import clamp_limit
from odoo.addons.mail.tools.discuss import Store, add_guest_to_context

_debug = DebugLog(__name__)

MENTIONED_LIMIT = 3
RECENT_LIMIT = 6


class SearchController(http.Controller):
    @http.route(
        "/discuss/search",
        methods=["POST"],
        type="jsonrpc",
        auth="public",
        readonly=True,
    )
    @add_guest_to_context
    def search(self, term: str, limit: int = 10) -> dict:
        limit = clamp_limit(limit, default=10)
        store = Store()
        result = self._search_results_to_store(store, search_term=term, limit=limit)
        return {**result, "store_data": store.get_result()}

    def _search_results_to_store(
        self, store: Store, search_term: str, limit: int
    ) -> dict[str, list[int]]:
        Channel = request.env["discuss.channel"]
        named_domain = Domain("name", "ilike", search_term) & Domain(
            "channel_type", "in", Channel._types_searchable_by_name()
        )
        base_domain = named_domain
        if not request.env.user._is_public():
            # a member reads the names of the other members of its conversations:
            # the persona match bypasses the persona rules, the outer is_member
            # keeps it to the user's own conversations
            base_domain |= (
                Domain(
                    "channel_type", "in", Channel._member_based_naming_channel_types()
                )
                & Domain("name", "=", False)
                & Domain("is_member", "=", True)
                & Domain(
                    "channel_member_ids",
                    "any!",
                    Domain("partner_id", "any!", Domain("name", "ilike", search_term))
                    | Domain("guest_id", "any!", Domain("name", "ilike", search_term)),
                )
            )
        priority_conditions = [
            Domain("is_member", "=", True) & base_domain,
            base_domain,
        ]
        channels = Channel
        for domain in priority_conditions:
            remaining_limit = limit - len(channels)
            if remaining_limit <= 0:
                break
            query = channels._search(
                Domain("id", "not in", channels.ids) & domain,
                limit=remaining_limit,
                order="is_favorite DESC, id",
            )
            channels |= channels.browse(query)
        result = {"channel_ids": channels.ids}
        listed = channels
        if not request.env.user._is_public():
            if not search_term:
                mentioned = Channel.search(
                    DiscussMessagingMenuController._get_menu_important_channels_domain()
                    & Domain("is_member", "=", True),
                    limit=MENTIONED_LIMIT,
                    order="last_interest_dt DESC, id DESC",
                )
                recent = Channel.search(
                    [("is_member", "=", True)],
                    limit=RECENT_LIMIT,
                    order="last_interest_dt DESC, id DESC",
                )
                result["mentioned_channel_ids"] = mentioned.ids
                result["recent_channel_ids"] = recent.ids
                listed |= mentioned | recent
            invites = request.env["res.partner"]._search_for_channel_invite(
                store, search_term=search_term, limit=limit
            )
            partners = request.env["res.partner"].browse(invites["partner_ids"])
            listed |= partners._get_self_chats()
        _debug.logic(
            "channel_search",
            limit=limit,
            channels=len(channels),
            listed=len(listed),
            public=request.env.user._is_public(),
        )
        store.add(listed)
        return result
