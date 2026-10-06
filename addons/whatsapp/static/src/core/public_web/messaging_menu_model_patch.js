/** @odoo-module native */
import {
    MENU_TABS,
    MessagingMenu,
} from "@mail/core/public_web/messaging_menu/messaging_menu_model";
import { fields } from "@mail/model/misc";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

MENU_TABS.WHATSAPP = "whatsapp";

patch(MessagingMenu.prototype, {
    setup() {
        super.setup();
        this.whatsappTab = fields.One("MessagingMenuTab", {
            compute() {
                return {
                    id: MENU_TABS.WHATSAPP,
                    recordType: "discuss.channel",
                    channelTypes: ["whatsapp"],
                    includesChannel: (channel) =>
                        Boolean(
                            channel.self_member_id?.is_pinned ||
                            channel.isLocallyPinned,
                        ),
                    icon: "fa-brands fa-whatsapp",
                    sequence: 80,
                    label: _t("WhatsApp"),
                    hideWhenEmpty: true,
                    emptyState: { title: _t("No WhatsApp conversation yet.") },
                    filters: [
                        {
                            id: "whatsapp_unread",
                            text: _t("Unread"),
                            includesChannel: (channel) => channel.isUnread,
                        },
                    ],
                };
            },
        });
    },
});
