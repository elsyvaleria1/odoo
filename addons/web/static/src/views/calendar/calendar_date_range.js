// @ts-check
/** @odoo-module native */

import {
    endOf,
    getStartOfLocalWeek,
    serializeDate,
    serializeDateTime,
    startOf,
} from "@web/core/l10n/dates";

/**
 * @param {"day" | "week" | "month" | "year"} scale
 * @param {Temporal.ZonedDateTime} date
 * @param {boolean} monthOverflow
 * @returns {{ start: Temporal.ZonedDateTime, end: Temporal.ZonedDateTime }}
 */
export function computeCalendarRange(scale, date, monthOverflow) {
    if (scale === "week" || (scale === "month" && monthOverflow)) {
        const start = getStartOfLocalWeek(
            scale === "week" ? date : startOf(date, "month"),
        );
        const end = endOf(
            start.add({ weeks: scale === "week" ? 1 : 6 }).subtract({ days: 1 }),
            "day",
        );
        return { start, end };
    }
    return { start: startOf(date, scale), end: endOf(date, scale) };
}

/**
 * @param {{ date_start: string, date_stop?: string, date_delay?: string }} fieldMapping
 * @param {"date" | "datetime"} dateStartType
 * @param {{ start: any, end: any }} range
 * @param {any} [dateDelayFloor]
 * @returns {any[][]}
 */
export function computeRangeDomain(fieldMapping, dateStartType, range, dateDelayFloor) {
    const serializeFn = dateStartType === "date" ? serializeDate : serializeDateTime;
    const formattedEnd = serializeFn(range.end);
    const formattedStart = serializeFn(range.start);

    const domain = [[fieldMapping.date_start, "<=", formattedEnd]];
    if (fieldMapping.date_stop) {
        domain.push([fieldMapping.date_stop, ">=", formattedStart]);
    } else if (!fieldMapping.date_delay) {
        domain.push([fieldMapping.date_start, ">=", formattedStart]);
    } else if (dateDelayFloor) {
        domain.push([fieldMapping.date_start, ">=", serializeFn(dateDelayFloor)]);
    }
    return domain;
}

export const DEFAULT_DELAY_HOURS = 1;

/**
 * @param {any} delay
 * @returns {number}
 */
export function delayHours(delay) {
    return typeof delay === "number" ? Math.max(delay, 0) : DEFAULT_DELAY_HOURS;
}

/**
 * @param {Record<string, { filters: { active: boolean, value: any }[] }>} filterSections
 * @param {Record<string, { writeResModel?: string }>} filtersInfo
 * @returns {any[][]}
 */
export function computeFiltersDomain(filterSections, filtersInfo) {
    const authorizedValues = {};
    const avoidValues = {};

    for (const [fieldName, filterSection] of Object.entries(filterSections)) {
        const filterSectionInfo = filtersInfo[fieldName];
        for (const filter of filterSection.filters) {
            if (filterSectionInfo.writeResModel) {
                if (!authorizedValues[fieldName]) {
                    authorizedValues[fieldName] = [];
                }
                if (filter.active) {
                    authorizedValues[fieldName].push(filter.value);
                }
            } else {
                if (!filter.active) {
                    if (!avoidValues[fieldName]) {
                        avoidValues[fieldName] = [];
                    }
                    avoidValues[fieldName].push(filter.value);
                }
            }
        }
    }

    const domain = [];
    for (const field of Object.keys(authorizedValues)) {
        domain.push([field, "in", authorizedValues[field]]);
    }
    for (const field of Object.keys(avoidValues)) {
        if (avoidValues[field].length > 0) {
            domain.push([field, "not in", avoidValues[field]]);
        }
    }
    return domain;
}
