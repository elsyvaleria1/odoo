// @ts-check
/** @odoo-module native */
import { MessagingMenu } from "@mail/core/public_web/messaging_menu/messaging_menu";
import { cleanTerm } from "@mail/utils/common/format";
import { makeLogger } from "@web/core/debug/debug_logger";
import { patch } from "@web/core/utils/patch";

const log = makeLogger("mail.messaging_menu");

patch(MessagingMenu.prototype, {
    /** @returns {import("models").DiscussChannel[]} */
    get channels() {
        const tab = this.activeTab;
        if (!tab || tab.recordType !== "discuss.channel") {
            return [];
        }
        const searchTerm = cleanTerm(this.state.searchTerm);
        return tab
            .getSortedChannels(this.activeFilters)
            .filter(
                (channel) =>
                    !searchTerm || cleanTerm(channel.displayName).includes(searchTerm),
            );
    },
    get itemCount() {
        return super.itemCount + this.channels.length;
    },
    /**
     * @param {import("models").DiscussChannel} channel
     * @param {{isMarkAsRead?: boolean}} [options]
     */
    onClickChannel(channel, { isMarkAsRead } = {}) {
        log.logic("onClickChannel", () => ({ channel: channel.localId, isMarkAsRead }));
        if (isMarkAsRead) {
            channel.markAsRead();
            if (channel.needactionMessages.length > 0) {
                channel.markAllMessagesAsRead();
            }
            return;
        }
        channel.open({ focus: true, fromMessagingMenu: true, bypassCompact: true });
        this.close();
    },
});
