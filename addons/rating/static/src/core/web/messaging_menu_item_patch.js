/** @odoo-module native */
import { MessagingMenuItem } from "@mail/core/public_web/messaging_menu/messaging_menu_item";
import { patch } from "@web/core/utils/patch";

patch(MessagingMenuItem.prototype, {
    get notificationItemProps() {
        const props = super.notificationItemProps;
        const message = this.message ?? this.channelPreviewMessage;
        if (props && message?.rating_id) {
            return { ...props, rating: message.rating_id };
        }
        return props;
    },
});
