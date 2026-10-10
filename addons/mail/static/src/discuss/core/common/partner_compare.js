// @ts-check
/** @odoo-module native */
import { partnerCompareRegistry } from "@mail/core/common/partner_compare";

partnerCompareRegistry.add(
    "discuss.recent-chats",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @param {Object} params
     * @param {{recentChatIndexByPartnerId: Map<number, number>}} params.context
     * @returns {number|undefined}
     */
    (p1, p2, { context: { recentChatIndexByPartnerId } }) => {
        const index1 = recentChatIndexByPartnerId.get(p1.id) ?? Infinity;
        const index2 = recentChatIndexByPartnerId.get(p2.id) ?? Infinity;
        if (index1 !== index2) {
            return index1 < index2 ? -1 : 1;
        }
    },
    { sequence: 45 },
);

partnerCompareRegistry.add(
    "discuss.members",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @param {Object} params
     * @param {import("models").Thread} [params.thread]
     * @param {{memberPartnerIds: Set<number>}} params.context
     * @returns {number|undefined}
     */
    (p1, p2, { thread, context: { memberPartnerIds } }) => {
        if (thread?.isChannelKind) {
            const isMember1 = memberPartnerIds.has(p1.id);
            const isMember2 = memberPartnerIds.has(p2.id);
            if (isMember1 && !isMember2) {
                return -1;
            }
            if (!isMember1 && isMember2) {
                return 1;
            }
        }
    },
    { sequence: 40 },
);
