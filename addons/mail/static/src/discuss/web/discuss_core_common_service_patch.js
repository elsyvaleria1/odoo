// @ts-check
/** @odoo-module native */
import { DiscussCoreCommon } from "@mail/discuss/core/common/discuss_core_common_service";
import { applyCounterDelta } from "@mail/utils/common/counters";
import { makeLogger } from "@web/core/debug/debug_logger";
import { patch } from "@web/core/utils/patch";

const log = makeLogger("mail.bus");
patch(DiscussCoreCommon.prototype, {
    /**
     * @param {import("models").Thread} thread
     * @param {{ id: number}} metadata
     */
    _handleNotificationChannelDelete(thread, metadata) {
        const { id: notifId } = metadata;
        const starredMessages = Object.values(
            this.store["mail.message"].records,
        ).filter((message) => message.starred && message.thread?.eq(thread));
        for (const message of starredMessages) {
            message.starred = false;
        }
        applyCounterDelta(this.store, "starred_counter", -starredMessages.length, {
            busId: notifId,
        });
        log.logic("channel delete drops its counted messages", () => ({
            thread: thread.localId,
            starredRemoved: starredMessages.length,
            wasDiscussThread: thread.eq(this.store.discuss.thread),
        }));
        if (thread.eq(this.store.discuss.thread)) {
            this.store.discuss.thread = undefined;
        }
        return super._handleNotificationChannelDelete(thread, metadata);
    },
});
