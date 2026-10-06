/** @odoo-module native */
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { patch } from "@web/core/utils/patch";

patch(DiscussChannel.prototype, {
    get hasMemberList() {
        return false;
    },
    get hasAttachmentPanel() {
        return !this.isLivechat && super.hasAttachmentPanel;
    },
});
