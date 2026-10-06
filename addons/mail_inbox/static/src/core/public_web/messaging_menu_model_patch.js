/** @odoo-module native */
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { fields } from "@mail/model/misc";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.EMAIL = "email";

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        this.emailTab = fields.One("MessagingMenuTab", {
            compute() {
                return {
                    id: MENU_TABS.EMAIL,
                    recordType: "discuss.channel",
                    channelTypes: ["email"],
                    includesChannel: (channel) =>
                        Boolean(channel.self_member_id?.is_pinned),
                    icon: "fa-solid fa-envelope",
                    sequence: 25,
                    label: _t("Email"),
                    hideWhenEmpty: true,
                    emptyState: {
                        title: _t("No email yet!"),
                        subtitle: _t(
                            "Mail written to your inboxes arrives here, one conversation per correspondent.",
                        ),
                    },
                    filters: [
                        {
                            id: "email_unread",
                            text: _t("Unread"),
                            includesChannel: (channel) => channel.isUnread,
                        },
                    ],
                };
            },
        });
    },
});
