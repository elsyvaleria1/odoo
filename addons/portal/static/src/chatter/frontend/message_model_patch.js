/** @odoo-module native */
import { Message } from "@mail/core/common/message_model";
import { patch } from "@web/core/utils/patch";

patch(Message.prototype, {
    get allowsEdition() {
        return super.allowsEdition && Boolean(this.thread?.can_post);
    },
    get canToggleStar() {
        let result = super.canToggleStar;
        if (this.thread && this.thread.model !== "discuss.channel") {
            result = result && this.thread.hasReadAccess;
        }
        return result;
    },
});
