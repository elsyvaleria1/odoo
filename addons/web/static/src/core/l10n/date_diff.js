// @ts-check
/** @odoo-module native */

/**
 * @typedef {"years" | "quarters" | "months" | "weeks" | "days" | "hours" | "minutes" | "seconds" | "milliseconds"} DiffUnit
 */

/**
 * @param {Temporal.ZonedDateTime} earlier
 * @param {Temporal.ZonedDateTime} later
 */
function dayDiff(earlier, later) {
    return later.toPlainDate().since(earlier.toPlainDate(), { largestUnit: "days" })
        .days;
}

/** @type {Record<string, (earlier: Temporal.ZonedDateTime, later: Temporal.ZonedDateTime) => number>} */
const CALENDAR_DIFFERS = {
    years: (earlier, later) => later.year - earlier.year,
    quarters: (earlier, later) =>
        Math.ceil(later.month / 3) -
        Math.ceil(earlier.month / 3) +
        (later.year - earlier.year) * 4,
    months: (earlier, later) =>
        later.month - earlier.month + (later.year - earlier.year) * 12,
    weeks: (earlier, later) => {
        const days = dayDiff(earlier, later);
        return (days - (days % 7)) / 7;
    },
    days: dayDiff,
};

/** @type {Record<string, number>} */
const NANOSECONDS_PER_UNIT = {
    hours: 3.6e12,
    minutes: 6e10,
    seconds: 1e9,
    milliseconds: 1e6,
};

/**
 * @param {Temporal.ZonedDateTime} value
 * @param {string} unit
 * @param {number} count
 */
function addUnits(value, unit, count) {
    return unit === "quarters"
        ? value.add({ months: count * 3 })
        : value.add({ [unit]: count });
}

/**
 * @param {Temporal.ZonedDateTime} a
 * @param {Temporal.ZonedDateTime} b
 */
function nanosecondsBetween(a, b) {
    return Number(b.epochNanoseconds - a.epochNanoseconds);
}

/**
 * @param {Temporal.ZonedDateTime} a
 * @param {Temporal.ZonedDateTime} b
 * @param {DiffUnit} unit
 * @returns {number}
 */
export function diff(a, b, unit) {
    const other = b.withTimeZone(a.timeZoneId);
    const otherIsLater = Temporal.ZonedDateTime.compare(other, a) > 0;
    const earlier = otherIsLater ? a : other;
    const later = otherIsLater ? other : a;
    let result;
    const differ = CALENDAR_DIFFERS[unit];
    if (differ) {
        let count = differ(earlier, later);
        let highWater = addUnits(earlier, unit, count);
        let cursor;
        if (Temporal.ZonedDateTime.compare(highWater, later) > 0) {
            count--;
            cursor = addUnits(earlier, unit, count);
            if (Temporal.ZonedDateTime.compare(cursor, later) > 0) {
                highWater = cursor;
                count--;
                cursor = addUnits(earlier, unit, count);
            }
        } else {
            cursor = highWater;
        }
        if (Temporal.ZonedDateTime.compare(highWater, later) < 0) {
            highWater = addUnits(cursor, unit, 1);
        }
        const span = nanosecondsBetween(cursor, highWater);
        result = count + (span ? nanosecondsBetween(cursor, later) / span : 0);
    } else {
        result = nanosecondsBetween(earlier, later) / NANOSECONDS_PER_UNIT[unit];
    }
    return otherIsLater ? -result : result;
}
