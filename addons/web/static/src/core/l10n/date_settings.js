// @ts-check
/** @odoo-module native */

/**
 * What every date is read, shown and parsed in: the user's time zone, the
 * page's locale and its numbering system. Set once at boot, by
 * applyUserTimezone and applyDateLocale.
 */
export const dateSettings = {
    /** @type {string | null} */
    timeZone: null,
    /** @type {string | undefined} */
    locale: undefined,
    /** @type {string} */
    numberingSystem: "latn",
    twoDigitCutoffYear: 60,
};

/** @returns {string} */
export function userTimeZone() {
    return dateSettings.timeZone ?? Temporal.Now.timeZoneId();
}

/** @param {unknown} timeZone */
export function isValidTimeZone(timeZone) {
    if (typeof timeZone !== "string" || !timeZone) {
        return false;
    }
    try {
        Temporal.Now.plainDateISO(timeZone);
        return true;
    } catch {
        return false;
    }
}
