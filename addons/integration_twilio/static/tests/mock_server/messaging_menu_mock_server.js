import { messagingMenuHelpers } from "@mail/../tests/mock_server/messaging_menu_mock_server";
import { patch } from "@web/core/utils/patch";

patch(messagingMenuHelpers, {
    _getMenuTabPredicate(env, tabId) {
        if (tabId !== "sms") {
            return super._getMenuTabPredicate(env, tabId);
        }
        return (channel) =>
            channel.channel_type === "sms" && Boolean(this._selfMember(env, channel));
    },
    _getMenuTabFilterPredicate(env, tabId, filterId) {
        if (`${tabId}/${filterId}` === "sms/sms_unread") {
            return (channel) => this._isUnread(env, channel);
        }
        return super._getMenuTabFilterPredicate(env, tabId, filterId);
    },
});
