// @ts-check
/** @odoo-module native */
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { patch } from "@web/core/utils/patch";
/** @type {Partial<import("models").DiscussChannel> & ThisType<import("models").DiscussChannel>} */
const ThreadPatch = {
    get isCallDisplayedInChatWindow() {
        return (
            super.isCallDisplayedInChatWindow &&
            (this.store.env.services.ui.isSmall || !this.store.discuss.isActive)
        );
    },
};
patch(DiscussChannel.prototype, ThreadPatch);
