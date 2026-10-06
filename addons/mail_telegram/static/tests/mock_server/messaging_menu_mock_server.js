import { messagingMenuHelpers } from "@mail/../tests/mock_server/messaging_menu_mock_server";
import { patch } from "@web/core/utils/patch";

patch(messagingMenuHelpers, {
    _getMenuTabPredicate(env, tabId) {
        if (tabId !== "telegram") {
            return super._getMenuTabPredicate(env, tabId);
        }
        return (channel) =>
            channel.channel_type === "telegram" &&
            !channel.parent_channel_id &&
            Boolean(this._selfMember(env, channel));
    },
    _getMenuTabFilterPredicate(env, tabId, filterId) {
        if (tabId === "telegram" && filterId === "telegram_unread") {
            return (channel) => this._isUnread(env, channel);
        }
        return super._getMenuTabFilterPredicate(env, tabId, filterId);
    },
});
