// @ts-check
/** @odoo-module native */
import { DiscussChannel } from "@mail/discuss/core/common/discuss_channel_model";
import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
patch(DiscussChannel.prototype, {
    setActiveURL() {
        browser.history.pushState(
            browser.history.state,
            null,
            `/discuss/channel/${this.id}${browser.location.search}`,
        );
    },
});
