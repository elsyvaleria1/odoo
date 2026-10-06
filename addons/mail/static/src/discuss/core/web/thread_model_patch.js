// @ts-check
/** @odoo-module native */
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { makeLogger } from "@web/core/debug/debug_logger";
import { patch } from "@web/core/utils/patch";

const log = makeLogger("mail.thread");
/** @type {Partial<import("models").DiscussChannel> & ThisType<import("models").DiscussChannel>} */
const modelPatch = {
    onPinStateUpdated() {
        super.onPinStateUpdated();
        if (
            !this.displayToSelf &&
            !this.isLocallyPinned &&
            this.eq(this.store.discuss.thread)
        ) {
            log.logic("unpinned discuss thread closed", () => ({
                thread: this.localId,
            }));
            this.store.discuss.thread = undefined;
            const tab = this.store.discuss.sidebarState.activeTab;
            if (this.store.discuss.isActive && tab) {
                this.store.discuss.setActiveURL(`discuss.tab_${tab.id}`);
            }
        }
    },
};
patch(DiscussChannel.prototype, modelPatch);
