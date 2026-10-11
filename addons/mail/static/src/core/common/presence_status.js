/** @odoo-module native */

export const BASE_IM_STATUSES = ["online", "away", "busy", "offline"];

export const REACHABLE_IM_STATUSES = ["online", "away", "busy"];

/** @type {Map<string, string>} decorated word -> the base word behind it */
const decorations = new Map();

/**
 * Teach mail that a module writes `decorated` into `im_status` where it means
 * `base`.
 *
 * `res.partner._compute_presence` and `res.users._compute_im_status` are
 * extension points: hr_homeworking writes `home_offline`, hr_holidays writes
 * `leave_offline`. Every `im_status === "offline"` in mail is then asking a
 * question the decoration has already destroyed, and every module that adds a
 * decoration has to find all of those sites again. Registering the pair once
 * answers them together, and the registrations are independent of each other and
 * of the order the modules load in.
 *
 * @param {string} decorated
 * @param {string} base one of BASE_IM_STATUSES
 */
export function registerImStatusDecoration(decorated, base) {
    if (!BASE_IM_STATUSES.includes(base)) {
        throw new Error(
            `registerImStatusDecoration("${decorated}", "${base}"): ` +
                `base must be one of ${BASE_IM_STATUSES.join(", ")}`,
        );
    }
    decorations.set(decorated, base);
}

/**
 * The undecorated presence word behind whatever is in `im_status`.
 *
 * Returns the value unchanged when no module has claimed it, so mail's own
 * words, "bot", "im_partner" and anything unknown pass through.
 *
 * @param {string|undefined|false} imStatus
 * @returns {string|undefined|false}
 */
export function baseImStatus(imStatus) {
    if (typeof imStatus !== "string") {
        return imStatus;
    }
    return decorations.get(imStatus) ?? imStatus;
}

export function reachableDecoratedImStatuses() {
    return [...decorations]
        .filter(([, base]) => REACHABLE_IM_STATUSES.includes(base))
        .map(([decorated]) => decorated);
}

export function registeredImStatusDecorations() {
    return new Map(decorations);
}
