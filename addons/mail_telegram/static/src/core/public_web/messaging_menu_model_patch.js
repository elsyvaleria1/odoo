/** @odoo-module native */
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { fields } from "@mail/model/misc";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.TELEGRAM = "telegram";

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        this.telegramTab = fields.One("MessagingMenuTab", {
            compute() {
                return {
                    id: MENU_TABS.TELEGRAM,
                    recordType: "discuss.channel",
                    channelTypes: ["telegram"],
                    includesChannel: (channel) =>
                        !channel.parent_channel_id && Boolean(channel.self_member_id),
                    icon: "fa-brands fa-telegram",
                    sequence: 85,
                    label: _t("Telegram"),
                    hideWhenEmpty: true,
                    emptyState: { title: _t("No Telegram group is connected yet.") },
                    filters: [
                        {
                            id: "telegram_unread",
                            text: _t("Unread"),
                            includesChannel: (channel) => channel.isUnread,
                        },
                    ],
                };
            },
        });
    },
});
