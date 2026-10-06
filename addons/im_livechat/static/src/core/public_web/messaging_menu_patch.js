/** @odoo-module native */
import { MessagingMenu } from "@mail/core/public_web/messaging_menu/messaging_menu";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

export const LIVECHAT_CHANNEL_PLUGIN_FILTER = "im_livechat.livechat_channel";

patch(MessagingMenu.prototype, {
    get pluginFilterGroups() {
        const groups = super.pluginFilterGroups;
        const menu = this.store.messagingMenu;
        if (!this.activeTab?.eq(menu.livechatTab)) {
            return groups;
        }
        const filters = menu.livechatChannelFilters;
        if (!filters.length) {
            return groups;
        }
        return [
            ...groups,
            {
                key: LIVECHAT_CHANNEL_PLUGIN_FILTER,
                text: _t("Live Chat Channel"),
                filters,
            },
        ];
    },
});
