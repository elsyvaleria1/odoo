import { messagingMenuHelpers } from "@mail/../tests/mock_server/messaging_menu_mock_server";
import { patch } from "@web/core/utils/patch";

patch(messagingMenuHelpers, {
    _getMenuTabPredicate(env, tabId) {
        if (tabId !== "whatsapp") {
            return super._getMenuTabPredicate(env, tabId);
        }
        return (channel) =>
            channel.channel_type === "whatsapp" &&
            Boolean(this._selfMember(env, channel)?.is_pinned);
    },
    _getMenuTabFilterPredicate(env, tabId, filterId) {
        if (tabId === "whatsapp" && filterId === "whatsapp_unread") {
            return (channel) => this._isUnread(env, channel);
        }
        return super._getMenuTabFilterPredicate(env, tabId, filterId);
    },
});
