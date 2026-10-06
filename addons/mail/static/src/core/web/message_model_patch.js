// @ts-check
/** @odoo-module native */
import { Message } from "@mail/core/common/message_model";
import { applyCounterDelta, snapshotCounter } from "@mail/utils/common/counters";
import { makeLogger } from "@web/core/debug/debug_logger";
import { patch } from "@web/core/utils/patch";

const log = makeLogger("mail.message");
/** @type {Partial<import("models").Message> & ThisType<import("models").Message>} */
const messagePatch = {
    /** @param {import("models").Thread} thread */
    canReplyAll(thread) {
        return this.canForward(thread) && !this.isNote;
    },
    /** @param {import("models").Thread} thread */
    canForward(thread) {
        if (!thread) {
            return false;
        }
        return (
            !thread.isChannelKind && ["comment", "email"].includes(this.message_type)
        );
    },
    async toggleStar() {
        const willStar = !this.starred;
        const counterSnapshot = snapshotCounter(this.store, "starred_counter");
        log.logic("toggleStar optimistic", () => ({ id: this.id, willStar }));
        this.starred = willStar;
        applyCounterDelta(this.store, "starred_counter", willStar ? 1 : -1);
        const id = Number(this.id);
        const pending = this.store.pendingStarToggles.get(id) ?? [];
        pending.push(willStar);
        this.store.pendingStarToggles.set(id, pending);
        try {
            await super.toggleStar(...arguments);
        } catch (error) {
            log.logic("toggleStar rollback", () => ({ id: this.id, willStar }));
            const index = pending.lastIndexOf(willStar);
            if (index !== -1) {
                pending.splice(index, 1);
            }
            if (!pending.length) {
                this.store.pendingStarToggles.delete(id);
            }
            this.starred = !willStar;
            counterSnapshot.restore();
            throw error;
        }
    },
};
patch(Message.prototype, messagePatch);
