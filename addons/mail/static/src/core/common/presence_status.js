/** @odoo-module native */

export const BASE_IM_STATUSES = ["online", "away", "busy", "offline"];

export const REACHABLE_IM_STATUSES = ["online", "away", "busy"];

/** @type {Map<string, string>} */
const decorations = new Map();

/**
 * @param {string} decorated
 * @param {string} base
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
