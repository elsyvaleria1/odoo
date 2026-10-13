/** @odoo-module native */

import {
    deserializeDate,
    deserializeDateTime,
    endOf,
    serializeDate,
    serializeDateTime,
    toDateTime,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { inRangeProviderRegistry } from "@web/core/tree";

/** @type {Array<Object>} */
let ranges = [];

/** @param {Array<Object>} loadedRanges */
export function setDateRanges(loadedRanges) {
    ranges = loadedRanges || [];
}

/**
 * @param {string} date
 * @param {string} fieldType
 * @param {boolean} endOfDay
 * @returns {string}
 */
function bound(date, fieldType, endOfDay) {
    if (fieldType === "date") {
        return date;
    }
    const dayStart = toDateTime(deserializeDate(date));
    return serializeDateTime(endOfDay ? endOf(dayStart, "day") : dayStart);
}

/**
 * @param {string} value
 * @param {string} fieldType
 * @returns {string}
 */
function toDate(value, fieldType) {
    if (fieldType === "date") {
        return value;
    }
    return serializeDate(deserializeDateTime(value));
}

/**
 * @param {number} id
 * @returns {string}
 */
function optionId(id) {
    return `date_range:${id}`;
}

inRangeProviderRegistry.add("date_range", {
    label: _t("Periods"),

    getOptions(fieldType) {
        if (!["date", "datetime"].includes(fieldType)) {
            return [];
        }
        return ranges.map((range) => ({
            id: optionId(range.id),
            label: range.name,
            group: range.type_id ? range.type_id[1] : undefined,
        }));
    },

    resolve(id, fieldType) {
        if (!["date", "datetime"].includes(fieldType)) {
            return null;
        }
        const range = ranges.find((r) => optionId(r.id) === id);
        if (!range) {
            return null;
        }
        return [
            bound(range.date_start, fieldType, false),
            bound(range.date_end, fieldType, true),
        ];
    },

    match(fieldType, start, end) {
        if (!["date", "datetime"].includes(fieldType) || !start || !end) {
            return null;
        }
        if (typeof start !== "string" || typeof end !== "string") {
            return null;
        }
        const startDate = toDate(start, fieldType);
        const endDate = toDate(end, fieldType);
        const range = ranges.find(
            (r) => r.date_start === startDate && r.date_end === endDate,
        );
        return range ? optionId(range.id) : null;
    },
});
