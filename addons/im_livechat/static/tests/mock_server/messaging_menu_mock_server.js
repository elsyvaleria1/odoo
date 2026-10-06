import { messagingMenuHelpers } from "@mail/../tests/mock_server/messaging_menu_mock_server";
import { serverState } from "@web/../tests/web_test_helpers";
import { patch } from "@web/core/utils/patch";

patch(messagingMenuHelpers, {
    _getMenuTabPredicate(env, tabId) {
        if (tabId !== "livechat") {
            return super._getMenuTabPredicate(env, tabId);
        }
        const hasLivechatAccess = Boolean(
            env.user?.group_ids.includes(serverState.groupLivechatId),
        );
        return (channel) =>
            channel.channel_type === "livechat" &&
            (Boolean(this._selfMember(env, channel)?.is_pinned) ||
                (hasLivechatAccess && channel.livechat_status === "need_help"));
    },
    _getMenuTabFilterPredicate(env, tabId, filterId) {
        switch (`${tabId}/${filterId}`) {
            case "livechat/livechat_unread":
                return (channel) => this._isUnread(env, channel);
            case "livechat/livechat_need_help":
                return (channel) => channel.livechat_status === "need_help";
            default: {
                const livechatChannelId =
                    tabId === "livechat" &&
                    /^livechat_channel_([1-9]\d*)$/.exec(filterId)?.[1];
                if (livechatChannelId) {
                    return (channel) =>
                        channel.livechat_channel_id === Number(livechatChannelId);
                }
                return super._getMenuTabFilterPredicate(env, tabId, filterId);
            }
        }
    },
});
