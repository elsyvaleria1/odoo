/** @odoo-module native */
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { fields } from "@mail/model/misc";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.SMS = "sms";

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        this.smsTab = fields.One("MessagingMenuTab", {
            compute() {
                return {
                    id: MENU_TABS.SMS,
                    recordType: "discuss.channel",
                    channelTypes: ["sms"],
                    includesChannel: (channel) => Boolean(channel.self_member_id),
                    icon: "fa-commenting",
                    sequence: 82,
                    label: _t("SMS"),
                    hideWhenEmpty: true,
                    emptyState: { title: _t("No SMS conversation yet.") },
                    filters: [
                        {
                            id: "sms_unread",
                            text: _t("Unread"),
                            includesChannel: (channel) => channel.isUnread,
                        },
                    ],
                };
            },
        });
    },
});
