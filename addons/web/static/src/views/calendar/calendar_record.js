// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import {
    compareDates,
    deserializeDate,
    deserializeDateTime,
    diff,
    hasSame,
    toDateTime,
} from "@web/core/l10n/dates";

import { DEFAULT_DELAY_HOURS, delayHours } from "./calendar_date_range.js";

const log = makeLogger("web.view.calendar");

/**
 * @param {Record<string, any>} rawRecord
 * @param {Object} options
 * @param {Record<string, any>} options.fields
 * @param {{ date_start: string, date_stop?: string, date_delay?: string, all_day?: string,
 * color?: string, create_name_field?: string }} options.fieldMapping
 * @param {boolean} options.isTimeHidden
 * @param {string} options.scale
 * @param {boolean} options.isSmall
 * @returns {{ id: number, title: string, isAllDay: boolean, start: any, startType: string,
 * end: any, endType: string, duration: number, colorIndex: any,
 * isHatched: boolean, isStriked: boolean, isTimeHidden: boolean,
 * isMonth: boolean, isSmall: boolean, rawRecord: Record<string, any> }}
 */
export function normalizeCalendarRecord(
    rawRecord,
    { fields, fieldMapping, isTimeHidden, scale, isSmall },
) {
    const startType = fields[fieldMapping.date_start].type;
    const isAllDay =
        startType === "date" ||
        (fieldMapping.all_day && rawRecord[fieldMapping.all_day]) ||
        false;
    /** @param {string} value */
    const deserialize = (value) =>
        isAllDay ? toDateTime(deserializeDate(value)) : deserializeDateTime(value);
    const start = deserialize(rawRecord[fieldMapping.date_start]);

    let end = start;
    let endType = startType;
    if (fieldMapping.date_stop) {
        endType = fields[fieldMapping.date_stop].type;
        const stop = rawRecord[fieldMapping.date_stop];
        end = stop ? deserialize(stop) : null;
    }
    const delay = fieldMapping.date_delay
        ? rawRecord[fieldMapping.date_delay]
        : undefined;
    let duration;
    if (fieldMapping.date_stop) {
        duration = end
            ? Math.max(diff(isAllDay ? end.add({ days: 1 }) : end, start, "hours"), 0)
            : DEFAULT_DELAY_HOURS;
    } else {
        duration = delayHours(delay);
        end = start.add({ hours: duration });
    }
    log.logic("recordEnd", () => ({
        id: rawRecord.id,
        delay: delay ?? null,
        duration,
        endFrom: fieldMapping.date_stop ? "date_stop" : "date_delay",
        zeroLength: Boolean(end) && compareDates(end, start) <= 0,
    }));

    const showTime =
        !(fieldMapping.all_day && rawRecord[fieldMapping.all_day]) &&
        startType !== "date" &&
        Boolean(end) &&
        hasSame(start, end, "day");

    const colorValue = rawRecord[/** @type {string} */ (fieldMapping.color)];
    const colorIndex = Array.isArray(colorValue) ? colorValue[0] : colorValue;

    const title = rawRecord[fieldMapping.create_name_field || "display_name"];

    return {
        id: rawRecord.id,
        title,
        isAllDay,
        start,
        startType,
        end,
        endType,
        duration,
        colorIndex,
        isHatched: rawRecord["is_hatched"] || false,
        isStriked: rawRecord["is_striked"] || false,
        isTimeHidden: isTimeHidden || !showTime,
        isMonth: scale === "month",
        isSmall,
        rawRecord,
    };
}
