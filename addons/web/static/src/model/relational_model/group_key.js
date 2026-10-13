// @ts-check
/** @odoo-module native */

import { isDateOrDateTimeValue, toISO } from "@web/core/l10n/dates";

/**
 * @param {any} value
 * @returns {string}
 */
export function getGroupKey(value) {
    return (
        JSON.stringify(isDateOrDateTimeValue(value) ? toISO(value) : value) ??
        "undefined"
    );
}
