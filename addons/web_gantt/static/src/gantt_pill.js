/** @odoo-module native */
import { formatFloatTime } from "@web/core/formatters";
import {
    compareDates,
    DATE_SHORT,
    diff,
    endOf,
    serializeDate,
    serializeDateTime,
    toDateTime,
    toLocaleDateTimeString,
    toLocaleString,
} from "@web/core/l10n/dates";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { omit } from "@web/core/utils/collections/objects";

import { diffColumn } from "./gantt_helpers.js";

/** @typedef {Temporal.ZonedDateTime} DateTime */

const YEARLESS_DATE_FORMAT = omit(DATE_SHORT, "year");

/**
 * @param {Record<string, any>} record
 * @param {Object} params
 * @param {string} params.dateStartField
 * @param {string} params.dateStopField
 * @param {boolean} params.stopIsDate
 * @param {DateTime} params.globalStart
 * @param {DateTime} params.globalStop
 * @param {boolean} params.canEdit
 * @param {boolean} params.disableDrag
 * @returns {{ start: DateTime, stop: DateTime, disableDrag: boolean, disableStartResize: boolean, disableStopResize: boolean }}
 */
export function pillBounds(
    record,
    {
        dateStartField,
        dateStopField,
        stopIsDate,
        globalStart,
        globalStop,
        canEdit,
        disableDrag,
    },
) {
    const recordStart = toDateTime(record[dateStartField]);
    const recordStop = toDateTime(
        stopIsDate ? record[dateStopField].add({ days: 1 }) : record[dateStopField],
    );
    const startOutside = compareDates(recordStart, globalStart) < 0;
    const stopOutside = compareDates(recordStop, globalStop) > 0;
    const disableStartResize = !canEdit || startOutside;
    const disableStopResize = !canEdit || stopOutside;
    return {
        start: startOutside ? globalStart : recordStart,
        stop: stopOutside ? globalStop : recordStop,
        disableDrag: Boolean(disableDrag || disableStartResize || disableStopResize),
        disableStartResize,
        disableStopResize,
    };
}

/**
 * @param {Record<string, any>} record
 * @param {Record<string, { type: string }>} fields
 * @param {Record<string, string>} pillDecorations
 * @param {Record<string, any>} baseContext
 * @returns {string[]}
 */
export function pillDecorationClasses(record, fields, pillDecorations, baseContext) {
    const context = { ...baseContext };
    for (const [fieldName, value] of Object.entries(record)) {
        switch (fields[fieldName]?.type) {
            case "date":
                context[fieldName] = value ? serializeDate(value) : false;
                break;
            case "datetime":
                context[fieldName] = value ? serializeDateTime(value) : false;
                break;
            default:
                context[fieldName] = value;
        }
    }
    return Object.entries(pillDecorations)
        .filter(([, expr]) => evaluateBooleanExpr(expr, context))
        .map(([decoration]) => decoration);
}

/**
 * @param {number} hours
 * @returns {string}
 */
export function durationLabel(hours) {
    const text = formatFloatTime(hours, { noLeadingZeroHour: true }).replace(
        /(:00|:)/g,
        "h",
    );
    return ` (${text})`;
}

/**
 * @param {Object} params
 * @param {string} params.displayName
 * @param {DateTime} params.startDate
 * @param {DateTime} params.stopDate
 * @param {string} params.scaleId
 * @param {DateTime} params.rangeStart
 * @param {DateTime} params.rangeStop
 * @param {number} params.duration
 * @param {string} params.durationStr
 * @returns {string}
 */
export function pillLabel({
    displayName,
    startDate,
    stopDate,
    scaleId,
    rangeStart,
    rangeStop,
    duration,
    durationStr,
}) {
    const daysDelta = Math.floor(
        diffColumn(startDate.startOfDay(), stopDate.startOfDay(), "day"),
    );
    const spanAcrossDays =
        daysDelta &&
        (daysDelta > 2 ||
            (diff(endOf(startDate, "day"), startDate, "hours") >= 3 &&
                diff(stopDate, stopDate.startOfDay(), "hours") >= 3));

    const labels = [];
    if (scaleId === "year" && !spanAcrossDays) {
        labels.push(toLocaleString(startDate, YEARLESS_DATE_FORMAT));
    } else if (
        scaleId === "year" ||
        (spanAcrossDays &&
            (compareDates(startDate, rangeStart) < 0 ||
                compareDates(endOf(rangeStop, "day"), stopDate) < 0))
    ) {
        labels.push(toLocaleString(startDate, YEARLESS_DATE_FORMAT));
        labels.push(toLocaleString(stopDate, YEARLESS_DATE_FORMAT));
    }

    if (duration && !spanAcrossDays && ["week", "month"].includes(scaleId)) {
        labels.push(
            toLocaleDateTimeString(startDate, { showDate: false }),
            `${toLocaleDateTimeString(stopDate, { showDate: false })}${durationStr}`,
        );
    }

    const parts = [labels.join(" - ")];
    if (scaleId !== "month" || !duration || spanAcrossDays) {
        parts.push(displayName);
    }
    return parts.filter(Boolean).join(" ");
}
