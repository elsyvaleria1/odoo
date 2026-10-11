// @ts-check
/** @odoo-module native */
import { MailCoreCommon } from "@mail/core/common/mail_core_common_service";
import { applyCounterDelta } from "@mail/utils/common/counters";
import { patch } from "@web/core/utils/patch";
patch(MailCoreCommon.prototype, {
    /**
     * @param {{message_ids: number[], starred: boolean}} payload
     * @param {{id: number}} metadata
     */
    _handleNotificationToggleStar(payload, metadata) {
        const { id: notifId } = metadata;
        const { message_ids: messageIds, starred } = payload;
        super._handleNotificationToggleStar(payload, metadata);
        for (const id of messageIds) {
            const pending = this.store.pendingStarToggles.get(id);
            const index = pending?.indexOf(starred) ?? -1;
            if (index !== -1) {
                pending.splice(index, 1);
                if (!pending.length) {
                    this.store.pendingStarToggles.delete(id);
                }
                continue;
            }
            applyCounterDelta(this.store, "starred_counter", starred ? 1 : -1, {
                busId: notifId,
            });
        }
        if (
            starred &&
            messageIds.some((id) => !this.store["mail.message"].get({ id }))
        ) {
            this.store.messagingMenu?.bookmarkTab?.markStale();
        }
    },
});
