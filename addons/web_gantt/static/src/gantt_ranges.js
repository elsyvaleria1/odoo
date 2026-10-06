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
 *
 * @typedef Range -- what the user picks in the scale selector
 * @property {string} id
 * @property {string} description
 * @property {Scale} scale -- the granularity it draws at; shared between ranges
 */

export const PARTS = { full: 1, half: 2, quarter: 4 };
export const SCALES = {
    day: {
        // determines subcolumns
        cellPrecisions: { full: 60, half: 30, quarter: 15 },
        defaultPrecision: "full",
        time: "minute",
        unitDescription: _t("minutes"),

        // determines columns
        interval: "hour",
        minimalColumnWidth: 40,
        colHeaderTitle: (date) => formatValue(date, "DDDD, t"),

        // determines column groups
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
 * Formats a date to a special datetime string, in the user's locale settings.
 * It contains the week number, its period and the year if it is different from the current's
 *
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
 * Ranges and scales are two vocabularies, not two collections: a range is what
 * the user picks and a scale is the granularity it draws at, and the mapping is
 * many-to-one -- "month" and "quarter" are both drawn at month granularity.
 * They were once two parallel maps, both keyed by range id, and the scale one
 * was routinely searched by scale id; that works only because four of the five
 * range ids happen to be spelled like a scale id. "quarter" is not, and
 * `<gantt scales="quarter"/>` used to resolve to `undefined` and take the whole
 * view down on the first render.
 *
 * There is one map now, keyed by range id, each entry carrying its own scale,
 * so a lookup can no longer be written in the wrong key space.
 *
 * @param {ScaleId} scaleId
 * @param {Record<string, Range>} ranges
 * @returns {Scale | undefined}
 */
function getScaleClosestTo(scaleId, ranges) {
    const available = Object.values(ranges).map((range) => range.scale);
    const byScaleId = (id) => available.find((scale) => scale.id === id);
    const scaleIds = Object.keys(SCALES);
    const index = scaleIds.indexOf(scaleId);
    // Coarser first, as a too-fine scale explodes the column count.
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
 * The first column boundary at or after `date`.
 *
 * @param {DateTime} date
 * @param {string} unit
 * @returns {DateTime}
 */
export function firstColumnAfter(date, unit) {
    const start = localStartOf(date, unit);
    return date.equals(start) ? date : start.add({ [`${unit}s`]: 1 });
}

/**
 * A range as the model keeps it: start before stop, at most ten years long
 * (clamped on the side the user did not just move), snapped outwards to the
 * column grid, with the focus date kept inside it when one is given.
 *
 * @param {Object} params
 * @param {DateTime} params.startDate
 * @param {DateTime} params.stopDate
 * @param {string} params.interval -- the scale's column unit
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
 * The custom range a context asks for: three months from the start it gives,
 * three months up to the stop it gives, exactly the pair when it gives both
 * (with today as the focus, kept inside), or three months around the focus
 * date when it gives neither.
 *
 * @param {Object} params
 * @param {DateTime | false} [params.startDate]
 * @param {DateTime | false} [params.stopDate]
 * @param {DateTime} params.focusDate -- what `initialDate` or today resolves to
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
