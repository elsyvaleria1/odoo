// @ts-check
/** @odoo-module native */
import { threadCompareRegistry } from "@mail/core/common/thread_compare";
import { compareDatetime } from "@mail/utils/common/misc";

/**
 * @param {import("models").Thread} thread1
 * @param {import("models").Thread} thread2
 * @returns {number|undefined}
 */
export function compareFavorites(thread1, thread2) {
    const aFavorite = Boolean(thread1.channel?.self_member_id?.is_favorite);
    const bFavorite = Boolean(thread2.channel?.self_member_id?.is_favorite);
    if (aFavorite !== bFavorite) {
        return aFavorite ? -1 : 1;
    }
}

threadCompareRegistry.add("mail.favorite", compareFavorites, { sequence: 10 });

threadCompareRegistry.add(
    "mail.unread",
    /**
     * @param {import("models").Thread} thread1
     * @param {import("models").Thread} thread2
     */
    (thread1, thread2) => {
        const aUnread = thread1.channel?.self_member_id?.message_unread_counter;
        const bUnread = thread2.channel?.self_member_id?.message_unread_counter;
        if (aUnread > 0 && bUnread === 0) {
            return -1;
        }
        if (bUnread > 0 && aUnread === 0) {
            return 1;
        }
    },
    { sequence: 20 },
);

threadCompareRegistry.add(
    "mail.last-interest",
    /**
     * @param {import("models").Thread} thread1
     * @param {import("models").Thread} thread2
     */
    (thread1, thread2) => {
        const aLastInterestDt = thread1.channel?.lastInterestDt;
        const bLastInterestDt = thread2.channel?.lastInterestDt;
        if (aLastInterestDt && bLastInterestDt) {
            const res = compareDatetime(bLastInterestDt, aLastInterestDt);
            if (res !== 0) {
                return res;
            }
        }
    },
    { sequence: 30 },
);
