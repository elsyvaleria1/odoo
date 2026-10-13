/** @odoo-module native */
import {
    clampDate,
    compareDates,
    formatValue,
    getLocalYearAndWeek,
    today,
    toLocaleString,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";

import { diffColumn, localStartOf } from "./gantt_helpers.js";

/**
 * @typedef {Temporal.ZonedDateTime} DateTime
 * @typedef {"day" | "week" | "month" | "year"} ScaleId
 * @typedef {"day" | "week" | "month" | "quarter" | "year"} RangeId
 * @typedef Range
 * @property {string} id
 * @property {string} description
 * @property {Scale} scale
 */

export const PARTS = { full: 1, half: 2, quarter: 4 };
export const SCALES = {
    day: {
        cellPrecisions: { full: 60, half: 30, quarter: 15 },
        defaultPrecision: "full",
        time: "minute",
        unitDescription: _t("minutes"),

        interval: "hour",
        minimalColumnWidth: 40,
        colHeaderTitle: (date) => formatValue(date, "DDDD, t"),

        unit: "day",
        groupHeaderFormatter: (date) => formatValue(date, "DDD"),
        groupHeaderTitle: (date) => formatValue(date, "DDDD"),
    },
    week: {
        cellPrecisions: { full: 24, half: 12 },
        defaultPrecision: "half",
        time: "hour",
        unitDescription: _t("hours"),

        interval: "day",
        minimalColumnWidth: 192,
        colHeaderFormatter: (date) => formatValue(date, "cccc d"),
        colHeaderTitle: (date) => formatValue(date, "DDDD"),

        unit: "week",
        groupHeaderFormatter: formatLocalWeekYear,
        groupHeaderTitle: formatLocalWeekYear,
    },
    month: {
        cellPrecisions: { full: 24, half: 12 },
        defaultPrecision: "half",
        time: "hour",
        unitDescription: _t("hours"),

        interval: "day",
        minimalColumnWidth: 52,
        colHeaderFormatter: (date) => formatValue(date, "dd"),
        colHeaderTitle: (date) => formatValue(date, "DDDD"),

        unit: "month",
        groupHeaderFormatter: (date, ui) =>
            formatValue(date, ui.isSmall ? "MMM yyyy" : "MMMM yyyy"),
        groupHeaderTitle: (date, ui) =>
            formatValue(date, ui.isSmall ? "MMM yyyy" : "MMMM yyyy"),
    },
    year: {
        cellPrecisions: { full: 1 },
        defaultPrecision: "full",
        time: "month",
        unitDescription: _t("months"),

        interval: "month",
        minimalColumnWidth: 100,
        colHeaderFormatter: (date, ui) =>
            formatValue(date, ui.isSmall ? "MMM" : "MMMM"),
        colHeaderTitle: (date, ui) =>
            formatValue(date, ui.isSmall ? "MMM yyyy" : "MMMM yyyy"),

        unit: "year",
        groupHeaderFormatter: (date) => formatValue(date, "yyyy"),
        groupHeaderTitle: (date) => formatValue(date, "yyyy"),
    },
};

/**
 * @param {DateTime} date
 * @returns {string}
 */
function formatLocalWeekYear(date) {
    const { year, week, startDate } = getLocalYearAndWeek(date);
    let result = _t(`Week %(week)s, %(startDate)s - %(endDate)s`, {
        week,
        startDate: toLocaleString(startDate, { month: "short", day: "numeric" }),
        endDate: toLocaleString(startDate.add({ days: 6 }), {
            month: "short",
            day: "numeric",
        }),
    });
    if (today().year !== year) {
        result += ` ${year}`;
    }
    return result;
}

/**
 * @param {ScaleId} scaleId
 * @param {Record<string, Range>} ranges
 * @returns {Scale | undefined}
 */
function getScaleClosestTo(scaleId, ranges) {
    const available = Object.values(ranges).map((range) => range.scale);
    const byScaleId = (id) => available.find((scale) => scale.id === id);
    const scaleIds = Object.keys(SCALES);
    const index = scaleIds.indexOf(scaleId);
    for (let j = index; j >= 0; j--) {
        const scale = byScaleId(scaleIds[j]);
        if (scale) {
            return scale;
        }
    }
    for (let j = index + 1; j < scaleIds.length; j++) {
        const scale = byScaleId(scaleIds[j]);
        if (scale) {
            return scale;
        }
    }
    return available[0];
}

export function getScaleForCustomRange(params) {
    const { ranges, startDate, stopDate } = params;
    const lengthInDays = diffColumn(startDate, stopDate, "day");
    let unit;
    if (lengthInDays < 6) {
        unit = "day";
    } else if (lengthInDays < 27) {
        unit = "week";
    } else if (lengthInDays < 364) {
        unit = "month";
    } else {
        unit = "year";
    }
    return getScaleClosestTo(unit, ranges);
}

export const RANGES = {
    day: { scaleId: "day", description: _t("Day") },
    week: { scaleId: "week", description: _t("Week") },
    month: { scaleId: "month", description: _t("Month") },
    quarter: { scaleId: "month", description: _t("Quarter") },
    year: { scaleId: "year", description: _t("Year") },
};

/**
 * @param {DateTime} date
 * @param {string} unit
 * @returns {DateTime}
 */
export function firstColumnAfter(date, unit) {
    const start = localStartOf(date, unit);
    return date.equals(start) ? date : start.add({ [`${unit}s`]: 1 });
}

/**
 * @param {Object} params
 * @param {DateTime} params.startDate
 * @param {DateTime} params.stopDate
 * @param {string} params.interval
 * @param {DateTime} [params.focusDate]
 * @returns {{ startDate: DateTime, stopDate: DateTime, globalStart: DateTime, globalStop: DateTime, focusDate?: DateTime }}
 */
export function normalizeRange({ startDate, stopDate, interval, focusDate }) {
    const exchanged = compareDates(startDate, stopDate) > 0;
    if (exchanged) {
        [startDate, stopDate] = [stopDate, startDate];
    }
    const tenYearsAfter = (date) => date.add({ years: 10 }).subtract({ days: 1 });
    if (compareDates(stopDate, tenYearsAfter(startDate)) > 0) {
        if (exchanged) {
            startDate = stopDate.subtract({ years: 10 }).add({ days: 1 });
        } else {
            stopDate = tenYearsAfter(startDate);
        }
    }
    const result = {
        startDate,
        stopDate,
        globalStart: localStartOf(startDate, interval),
        globalStop: firstColumnAfter(stopDate.add({ days: 1 }), interval),
    };
    if (focusDate) {
        result.focusDate = clampDate(focusDate, startDate, stopDate);
    }
    return result;
}

const CUSTOM_RANGE_UNIT = "month";
const CUSTOM_RANGE_COUNT = 3;

/**
 * @param {Object} params
 * @param {DateTime | false} [params.startDate]
 * @param {DateTime | false} [params.stopDate]
 * @param {DateTime} params.focusDate
 * @param {DateTime} params.today
 * @returns {{ focusDate: DateTime, startDate: DateTime, stopDate: DateTime }}
 */
export function customRangeAround({ startDate, stopDate, focusDate, today }) {
    const span = { [`${CUSTOM_RANGE_UNIT}s`]: CUSTOM_RANGE_COUNT };
    if (!startDate && !stopDate) {
        startDate = localStartOf(focusDate, CUSTOM_RANGE_UNIT);
        return {
            focusDate,
            startDate,
            stopDate: startDate.add(span).subtract({ days: 1 }),
        };
    }
    if (startDate && !stopDate) {
        const column = localStartOf(startDate, CUSTOM_RANGE_UNIT);
        return {
            focusDate: startDate,
            startDate,
            stopDate: column.add(span).subtract({ days: 1 }),
        };
    }
    if (!startDate && stopDate) {
        const column = firstColumnAfter(stopDate, CUSTOM_RANGE_UNIT);
        return { focusDate: stopDate, startDate: column.subtract(span), stopDate };
    }
    return {
        focusDate:
            compareDates(today, startDate) < 0
                ? startDate
                : compareDates(today, stopDate) > 0
                  ? stopDate
                  : today,
        startDate,
        stopDate,
    };
}
