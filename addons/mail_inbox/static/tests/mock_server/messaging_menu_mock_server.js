import { messagingMenuHelpers } from "@mail/../tests/mock_server/messaging_menu_mock_server";
import { patch } from "@web/core/utils/patch";

patch(messagingMenuHelpers, {
    _getMenuTabPredicate(env, tabId) {
        if (tabId !== "email") {
            return super._getMenuTabPredicate(env, tabId);
        }
        return (channel) =>
            channel.channel_type === "email" &&
            Boolean(this._selfMember(env, channel)?.is_pinned);
    },
    _getMenuTabFilterPredicate(env, tabId, filterId) {
        if (tabId === "email" && filterId === "email_unread") {
            return (channel) => this._isUnread(env, channel);
        }
        return super._getMenuTabFilterPredicate(env, tabId, filterId);
    },
});
