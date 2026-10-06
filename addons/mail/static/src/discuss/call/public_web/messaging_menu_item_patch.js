// @ts-check
/** @odoo-module native */
import { MessagingMenuItem } from "@mail/core/public_web/messaging_menu/messaging_menu_item";
import { CallParticipants } from "@mail/discuss/call/public_web/call_participants";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

Object.assign(MessagingMenuItem.components, { CallParticipants });

patch(MessagingMenuItem.prototype, {
    setup() {
        super.setup();
        this.rtc = useService("discuss.rtc");
    },
    get hasOngoingCall() {
        return Boolean(this.channel?.rtc_session_ids.length);
    },
});
