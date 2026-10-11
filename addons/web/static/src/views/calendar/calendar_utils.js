// @ts-check
/** @odoo-module native */

import { getCalendarColor as getColor } from "@web/core/colors/colors";
import { makeLogger } from "@web/core/debug/debug_logger";
import { compareDates, diff, formatValue, hasSame, toISO } from "@web/core/l10n/dates";

export { getColor };

const log = makeLogger("web.view.calendar");

export const ZERO_LENGTH_DRAWN_MINUTES = 15;

/**
 * @param {Object} record
 * @param {boolean} [forceAllDay=false]
 * @returns {{ id: number, title: string, start: string, end: string | null, allDay: boolean }}
 */
export function convertRecordToEvent(record, forceAllDay = false) {
    const allDay =
        forceAllDay ||
        record.isAllDay ||
        (Boolean(record.end) && diff(record.end, record.start, "hours") >= 24);
    let end = record.end;
    if (!end) {
        return {
            id: record.id,
            title: record.title,
            start: toISO(record.start),
            end: null,
            allDay,
        };
    }
    if (
        record.isAllDay ||
        (allDay && end.epochMilliseconds !== end.startOfDay().epochMilliseconds)
    ) {
        end = end.add({ days: 1 });
    } else if (!allDay && compareDates(end, record.start) <= 0) {
        end = record.start.add({ minutes: ZERO_LENGTH_DRAWN_MINUTES });
        log.logic("zeroLengthEvent", () => ({
            id: record.id,
            start: toISO(record.start),
            drawnEnd: toISO(end),
        }));
    }
    return {
        id: record.id,
        title: record.title,
        start: toISO(record.start),
        end: toISO(end),
        allDay,
    };
}

/**
 * @param {Array<{ type: string, value: any, label: string }>} filters
 * @param {string[]} typePriority
 * @returns {Array}
 */
export function sortCalendarFilters(filters, typePriority) {
    return filters.toSorted((a, b) => {
        if (a.type === b.type) {
            const va = a.value ? -1 : 0;
            const vb = b.value ? -1 : 0;
            if (a.type === "dynamic" && va !== vb) {
                return va - vb;
            }
            return a.label.localeCompare(b.label, undefined, {
                numeric: true,
                sensitivity: "base",
                ignorePunctuation: true,
            });
        } else {
            return typePriority.indexOf(a.type) - typePriority.indexOf(b.type);
        }
    });
}

/**
 * @param {any} start
 * @param {any} end
 * @returns {string}
 */
export function getFormattedDateSpan(start, end) {
    if (!end) {
        return formatValue(start, "DDD");
    }
    const isSameDay = hasSame(start, end, "day");

    if (!isSameDay && hasSame(start, end, "month")) {
        return `${formatValue(start, "LLLL d")}-${formatValue(end, "d, y")}`;
    } else {
        return isSameDay
            ? formatValue(start, "DDD")
            : `${formatValue(start, "DDD")} - ${formatValue(end, "DDD")}`;
    }
}

/**
 * @param {any} record
 * @returns {string[]}
 */
export function baseEventClassNames(record) {
    const classes = ["o_event"];
    if (!record) {
        return classes;
    }
    const color = getColor(record.colorIndex);
    if (typeof color === "number") {
        classes.push(`o_calendar_color_${color}`);
    } else if (typeof color !== "string") {
        classes.push("o_calendar_color_0");
    }
    if (record.isHatched) {
        classes.push("o_event_hatched");
    }
    if (record.isStriked) {
        classes.push("o_event_striked");
    }
    return classes;
}

/**
 * @param {HTMLElement} el
 * @param {{ id: string }} event
 * @param {any} record
 * @param {string[]} classes
 * @returns {void}
 */
export function paintMountedEvent(el, event, record, classes) {
    if (classes.length) {
        el.classList.add(...classes);
    }
    el.dataset.eventId = event.id;
    if (!record) {
        return;
    }
    const color = getColor(record.colorIndex);
    if (typeof color === "string") {
        el.style.backgroundColor = color;
    }
}
