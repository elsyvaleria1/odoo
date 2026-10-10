// @ts-check
/** @odoo-module native */
import { comparePrefixThenAlpha } from "@mail/utils/common/misc";
import { registry } from "@web/core/registry";
export const partnerCompareRegistry = registry.category("mail.partner_compare");

partnerCompareRegistry.add(
    "mail.archived-last-except-odoobot",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @returns {number|undefined}
     */
    (p1, p2) => {
        const p1active = p1.active || p1.eq(p1.store.odoobot);
        const p2active = p2.active || p2.eq(p2.store.odoobot);
        if (!p1active && p2active) {
            return 1;
        }
        if (!p2active && p1active) {
            return -1;
        }
    },
    { sequence: 5 },
);

partnerCompareRegistry.add(
    "mail.internal-users",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @returns {number|undefined}
     */
    (p1, p2) => {
        const isAInternalUser = p1.isInternalUser;
        const isBInternalUser = p2.isInternalUser;
        if (isAInternalUser && !isBInternalUser) {
            return -1;
        }
        if (!isAInternalUser && isBInternalUser) {
            return 1;
        }
    },
    { sequence: 35 },
);

partnerCompareRegistry.add(
    "mail.followers",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @param {Object} params
     * @param {{followerPartnerIds: Set<number>}} params.context
     * @returns {number|undefined}
     */
    (p1, p2, { context: { followerPartnerIds } }) => {
        const isFollower1 = followerPartnerIds.has(p1.id);
        const isFollower2 = followerPartnerIds.has(p2.id);
        if (isFollower1 !== isFollower2) {
            return isFollower1 ? -1 : 1;
        }
    },
    { sequence: 25 },
);

partnerCompareRegistry.add(
    "mail.name",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @param {Object} params
     * @param {string} params.searchTerm
     * @param {{cleanedName: (partner: import("models").ResPartner) => string}} params.context
     * @returns {number|undefined}
     */
    (p1, p2, { searchTerm, context: { cleanedName } }) =>
        comparePrefixThenAlpha(cleanedName(p1), cleanedName(p2), searchTerm) ||
        undefined,
    { sequence: 50 },
);

partnerCompareRegistry.add(
    "mail.email",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @param {Object} params
     * @param {string} params.searchTerm
     * @param {{cleanedEmail: (partner: import("models").ResPartner) => string}} params.context
     * @returns {number|undefined}
     */
    (p1, p2, { searchTerm, context: { cleanedEmail } }) =>
        comparePrefixThenAlpha(cleanedEmail(p1), cleanedEmail(p2), searchTerm) ||
        undefined,
    { sequence: 55 },
);

partnerCompareRegistry.add(
    "mail.id",
    /**
     * @param {import("models").ResPartner} p1
     * @param {import("models").ResPartner} p2
     * @returns {number}
     */
    (p1, p2) => p1.id - p2.id,
    { sequence: 75 },
);
