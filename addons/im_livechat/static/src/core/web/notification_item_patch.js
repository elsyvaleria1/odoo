/** @odoo-module native */
import { NotificationItem } from "@mail/core/public_web/notification_item";
import { patch } from "@web/core/utils/patch";

patch(NotificationItem.prototype, {
    get attClass() {
        const channel = this.props.thread?.channel;
        return {
            ...super.attClass,
            "o-livechat-selfMember": Boolean(channel?.self_member_id),
            "o-livechat-help": channel?.livechat_status === "need_help",
        };
    },
});
