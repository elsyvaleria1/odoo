// @ts-check
/** @odoo-module native */
import { formatLocalized } from "@web/core/l10n/date_format";
import {
    dateSettings,
    diff,
    hasSame,
    isDateValue,
    now,
    today,
} from "@web/core/l10n/dates";
import { user } from "@web/core/user";

/**
 * @param {Temporal.PlainDate | null | false | undefined} date
 * @returns {number}
 */
export function computeDelay(date) {
    if (!date) {
        return 0;
    }
    return diff(date, today(), "days");
}

/** @returns {number} */
export function getMsToTomorrow() {
    const current = now();
    return (
        current.add({ days: 1 }).startOfDay().epochMilliseconds -
        current.epochMilliseconds
    );
}

/**
 * @param {Temporal.ZonedDateTime | Temporal.PlainDate | null | false | undefined} value
 * @returns {boolean}
 */
export function isToday(value) {
    if (!value) {
        return false;
    }
    return isDateValue(value)
        ? hasSame(value, today(), "day")
        : hasSame(value, now(), "day");
}

/**
 * @param {Temporal.ZonedDateTime} value
 * @param {Intl.DateTimeFormatOptions} options
 * @returns {string}
 */
export function toUserLangString(value, options) {
    return formatLocalized(value, options, {
        locale: user.lang || dateSettings.locale,
        numberingSystem: dateSettings.numberingSystem,
    });
}
