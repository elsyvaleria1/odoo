// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { localization } from "@web/core/l10n/localization";
import { ensureArray } from "@web/core/utils/collections/arrays";

import { diff } from "./date_diff.js";
import { dateSettings, isValidTimeZone, userTimeZone } from "./date_settings.js";

/**
 * @typedef {Temporal.ZonedDateTime} DateTimeValue
 * @typedef {Temporal.PlainDate} DateValue
 * @typedef {DateValue | DateTimeValue} AnyDateValue
 * @typedef {"year" | "quarter" | "month" | "week" | "day" | "hour" | "minute" | "second"} DateUnit
 * @typedef {"years" | "quarters" | "months" | "weeks" | "days" | "hours" | "minutes" | "seconds" | "milliseconds"} DiffUnit
 * @typedef {{ year?: number, month?: number, day?: number, hour?: number, minute?: number, second?: number, millisecond?: number }} DateFields
 */

/**
 * @param {unknown} value
 * @returns {value is Temporal.ZonedDateTime}
 */
export function isDateTimeValue(value) {
    return value instanceof Temporal.ZonedDateTime;
}

/**
 * @param {unknown} value
 * @returns {value is Temporal.PlainDate}
 */
export function isDateValue(value) {
    return value instanceof Temporal.PlainDate;
}

/**
 * @param {unknown} value
 * @returns {value is AnyDateValue}
 */
export function isDateOrDateTimeValue(value) {
    return isDateValue(value) || isDateTimeValue(value);
}

/**
 * @param {DateValue} value
 * @returns {DateTimeValue}
 */
function atUTCMidnight(value) {
    return value.toZonedDateTime({ timeZone: "UTC" });
}

/**
 * @param {unknown} a
 * @param {unknown} b
 * @param {string} operation
 */
function assertSameKind(a, b, operation) {
    if (isDateValue(a) !== isDateValue(b)) {
        throw new TypeError(
            `${operation}: a date and a datetime do not compare; convert one with toDate or toDateTime`,
        );
    }
}

/**
 * @param {any} d1
 * @param {any} d2
 * @returns {boolean}
 */
export function areDatesEqual(d1, d2) {
    if (Array.isArray(d1) || Array.isArray(d2)) {
        d1 = ensureArray(d1);
        d2 = ensureArray(d2);
        return (
            d1.length === d2.length &&
            d1.every((/** @type {any} */ d1Val, /** @type {number} */ i) =>
                areDatesEqual(d1Val, d2[i]),
            )
        );
    }
    if (!d1 && !d2) {
        return true;
    }
    if (isDateTimeValue(d1) && isDateTimeValue(d2)) {
        return d1.epochNanoseconds === d2.epochNanoseconds;
    }
    if (isDateValue(d1) && isDateValue(d2)) {
        return d1.equals(d2);
    }
    return d1 === d2;
}

/**
 * @param {AnyDateValue} a
 * @param {AnyDateValue} b
 * @returns {number}
 */
export function compareDates(a, b) {
    assertSameKind(a, b, "compareDates");
    return isDateValue(a)
        ? Temporal.PlainDate.compare(a, /** @type {DateValue} */ (b))
        : Temporal.ZonedDateTime.compare(a, /** @type {DateTimeValue} */ (b));
}

/**
 * @template {AnyDateValue} T
 * @param {T} value
 * @param {T} [minDate]
 * @param {T} [maxDate]
 * @returns {T}
 */
export function clampDate(value, minDate, maxDate) {
    if (maxDate && compareDates(maxDate, value) < 0) {
        return maxDate;
    }
    if (minDate && compareDates(minDate, value) > 0) {
        return minDate;
    }
    return value;
}

/**
 * @template {AnyDateValue} T
 * @param {...T} values
 * @returns {T}
 */
export function minDate(...values) {
    return values.reduce((min, value) => (compareDates(value, min) < 0 ? value : min));
}

/**
 * @template {AnyDateValue} T
 * @param {...T} values
 * @returns {T}
 */
export function maxDate(...values) {
    return values.reduce((max, value) => (compareDates(value, max) > 0 ? value : max));
}

/**
 * @param {any} value
 * @param {[AnyDateValue, AnyDateValue]} range
 * @returns {boolean}
 */
export function isInRange(value, range) {
    if (!value || !range) {
        return false;
    }
    if (Array.isArray(value)) {
        const actualValues = value.filter(Boolean).sort(compareDates);
        if (actualValues.length < 2) {
            return isInRange(actualValues[0], range);
        }
        return (
            (compareDates(actualValues[0], range[0]) <= 0 &&
                compareDates(range[0], actualValues[1]) <= 0) ||
            (compareDates(range[0], actualValues[0]) <= 0 &&
                compareDates(actualValues[0], range[1]) <= 0)
        );
    }
    return compareDates(range[0], value) <= 0 && compareDates(value, range[1]) <= 0;
}

const log = makeLogger("web.l10n");

/** @type {Set<any>} */
const unknownZones = new Set();

/**
 * @param {any} [tz]
 * @returns {string}
 */
export function resolveZone(tz) {
    if (!tz || tz === "default") {
        return userTimeZone();
    }
    if (tz === "utc") {
        return "UTC";
    }
    if (isValidTimeZone(tz)) {
        return tz;
    }
    const firstSeen = !unknownZones.has(tz);
    log.logic("resolveZone:unknown", () => ({ tz: String(tz), firstSeen }));
    if (firstSeen) {
        unknownZones.add(tz);
        console.warn(
            `[l10n] ignoring an unknown tz ${JSON.stringify(tz)}; using the default ` +
                `zone. Using it would have made every date shown or read in it invalid.`,
        );
    }
    return userTimeZone();
}

/**
 * @param {string} [tz]
 * @returns {DateTimeValue}
 */
export function now(tz) {
    return Temporal.Now.zonedDateTimeISO(resolveZone(tz));
}

/**
 * @param {string} [tz]
 * @returns {DateValue}
 */
export function today(tz) {
    return now(tz).toPlainDate();
}

/**
 * @param {AnyDateValue} value
 * @param {string} [tz]
 * @returns {DateTimeValue}
 */
export function toDateTime(value, tz) {
    return isDateValue(value)
        ? value.toZonedDateTime({ timeZone: resolveZone(tz) })
        : value.withTimeZone(resolveZone(tz));
}

/**
 * @param {AnyDateValue} value
 * @returns {DateValue}
 */
export function toDate(value) {
    return isDateValue(value) ? value : value.toPlainDate();
}

const DATE_FIELD_ORDER = /** @type {const} */ ([
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
    "millisecond",
]);

/**
 * @param {DateFields} fields
 * @param {string} [tz]
 * @returns {DateTimeValue}
 */
export function dateTime(fields, tz) {
    const zone = resolveZone(tz);
    const given = /** @type {Record<string, number | undefined>} */ (fields);
    let largest = DATE_FIELD_ORDER.findIndex((unit) => given[unit] !== undefined);
    if (largest === -1) {
        largest = DATE_FIELD_ORDER.length;
    }
    const current = largest > 0 ? now(zone) : null;
    /** @type {Record<string, number>} */
    const values = {};
    for (const [index, unit] of DATE_FIELD_ORDER.entries()) {
        values[unit] =
            given[unit] ??
            (index < largest
                ? /** @type {Temporal.ZonedDateTime} */ (current)[unit]
                : unit === "month" || unit === "day"
                  ? 1
                  : 0);
    }
    return Temporal.ZonedDateTime.from(
        { .../** @type {any} */ (values), timeZone: zone },
        { overflow: "reject" },
    );
}

/**
 * @param {number} milliseconds
 * @param {string} [tz]
 * @returns {DateTimeValue}
 */
export function fromEpochMilliseconds(milliseconds, tz) {
    return Temporal.Instant.fromEpochMilliseconds(milliseconds).toZonedDateTimeISO(
        resolveZone(tz),
    );
}

/**
 * @param {Date} date
 * @param {string} [tz]
 * @returns {DateTimeValue}
 */
export function fromJSDate(date, tz) {
    return fromEpochMilliseconds(date.getTime(), tz);
}

/**
 * @param {AnyDateValue} value
 * @returns {Date}
 */
export function toJSDate(value) {
    return new Date((isDateValue(value) ? toDateTime(value) : value).epochMilliseconds);
}

const ISO_OFFSET = String.raw`(?:([Zz])|([+-]\d\d)(?::?(\d\d))?)`;
const IANA_ZONE = String.raw`[A-Za-z_+-]{1,256}(?::?\/[A-Za-z0-9_+-]{1,256}(?:\/[A-Za-z0-9_+-]{1,256})?)?`;
const ISO_TIME = String.raw`(\d\d)(?::?(\d\d)(?::?(\d\d)(?:[.,](\d{1,30}))?)?)?`;
const ISO_ZONE = `(?:${ISO_OFFSET}?(?:\\[(${IANA_ZONE})\\])?)?`;
const ISO_TIME_EXTENSION = `(?:[Tt]${ISO_TIME}${ISO_ZONE})?`;
const SQL_TIME = `${ISO_TIME} ?(?:${ISO_OFFSET}|(${IANA_ZONE}))?`;

/**
 * @typedef {"ymd" | "week" | "ordinal" | "time"} DateGrammar
 * @type {Record<DateGrammar, number>}
 */
const DATE_GROUPS = { ymd: 3, week: 3, ordinal: 2, time: 0 };

/** @type {[DateGrammar, RegExp][]} */
const ISO_GRAMMARS = [
    [
        "ymd",
        new RegExp(
            String.raw`^([+-]\d{6}|\d{4})(?:-?(\d\d)(?:-?(\d\d))?)?${ISO_TIME_EXTENSION}$`,
        ),
    ],
    [
        "week",
        new RegExp(String.raw`^(\d{4})-?W(\d\d)(?:-?(\d))?${ISO_TIME_EXTENSION}$`),
    ],
    ["ordinal", new RegExp(String.raw`^(\d{4})-?(\d{3})${ISO_TIME_EXTENSION}$`)],
    ["time", new RegExp(`^${ISO_TIME}${ISO_ZONE}$`)],
];

/** @type {[DateGrammar, RegExp][]} */
const SQL_GRAMMARS = [
    ["ymd", new RegExp(String.raw`^(\d{4})-(\d\d)-(\d\d)(?: ${SQL_TIME})?$`)],
    ["time", new RegExp(`^${SQL_TIME}$`)],
];

/**
 * @param {string | undefined} text
 * @param {number} [fallback]
 */
const toInt = (text, fallback) => (text === undefined ? fallback : Number(text));

/**
 * @param {DateGrammar} grammar
 * @param {(string | undefined)[]} groups
 * @param {string} zone
 * @returns {Temporal.PlainDate | null}
 */
function matchedDate(grammar, groups, zone) {
    switch (grammar) {
        case "ymd":
            return Temporal.PlainDate.from(
                {
                    year: Number(groups[0]),
                    month: /** @type {number} */ (toInt(groups[1], 1)),
                    day: /** @type {number} */ (toInt(groups[2], 1)),
                },
                { overflow: "reject" },
            );
        case "week": {
            const weekYear = Number(groups[0]);
            const week = Number(groups[1]);
            const weekday = /** @type {number} */ (toInt(groups[2], 1));
            const weeks = Temporal.PlainDate.from({
                year: weekYear,
                month: 12,
                day: 28,
            }).weekOfYear;
            if (
                week < 1 ||
                week > /** @type {number} */ (weeks) ||
                weekday < 1 ||
                weekday > 7
            ) {
                return null;
            }
            const jan4 = Temporal.PlainDate.from({ year: weekYear, month: 1, day: 4 });
            return jan4.add({ days: (week - 1) * 7 + weekday - jan4.dayOfWeek });
        }
        case "ordinal": {
            const year = Number(groups[0]);
            const ordinal = Number(groups[1]);
            const first = Temporal.PlainDate.from({ year, month: 1, day: 1 });
            if (ordinal < 1 || ordinal > first.daysInYear) {
                return null;
            }
            return first.add({ days: ordinal - 1 });
        }
        case "time":
            return Temporal.Now.plainDateISO(zone);
    }
}

/**
 * @param {string} text
 * @param {[DateGrammar, RegExp][]} grammars
 * @param {string} zone
 * @returns {DateTimeValue | null}
 */
function parseByGrammars(text, grammars, zone) {
    for (const [grammar, regex] of grammars) {
        const match = regex.exec(text);
        if (!match) {
            continue;
        }
        const groups = match.slice(1);
        const dateCount = DATE_GROUPS[grammar];
        const [hour, minute, second, fraction, utc, offsetHours, offsetMinutes, iana] =
            groups.slice(dateCount);
        let interpretation = zone;
        if (iana) {
            if (!isValidTimeZone(iana)) {
                return null;
            }
            interpretation = iana;
        } else if (utc || offsetHours) {
            const hours = Number(offsetHours ?? 0);
            const minutes = Number(offsetMinutes ?? 0);
            const negative = offsetHours?.startsWith("-");
            interpretation = `${negative ? "-" : "+"}${String(Math.abs(hours)).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
        }
        try {
            const date = matchedDate(grammar, groups, interpretation);
            if (!date) {
                return null;
            }
            const time = {
                hour: /** @type {number} */ (toInt(hour, 0)),
                minute: /** @type {number} */ (toInt(minute, 0)),
                second: /** @type {number} */ (toInt(second, 0)),
                millisecond: fraction
                    ? Math.floor(Number.parseFloat(`0.${fraction}`) * 1000)
                    : 0,
            };
            let day = date;
            if (time.hour === 24) {
                if (time.minute || time.second || time.millisecond) {
                    return null;
                }
                time.hour = 0;
                day = date.add({ days: 1 });
            }
            return day
                .toPlainDateTime(Temporal.PlainTime.from(time, { overflow: "reject" }))
                .toZonedDateTime(interpretation)
                .withTimeZone(zone);
        } catch {
            return null;
        }
    }
    return null;
}

/**
 * @param {string} text
 * @param {string} [tz]
 * @returns {DateTimeValue | null}
 */
export function parseISO(text, tz) {
    const zone = resolveZone(tz);
    return (
        parseByGrammars(text, ISO_GRAMMARS, zone) ??
        parseByGrammars(text, SQL_GRAMMARS, zone)
    );
}

/**
 * @param {string} text
 * @param {string} [tz]
 * @returns {DateTimeValue | null}
 */
export function parseSQL(text, tz) {
    return parseByGrammars(text, SQL_GRAMMARS, resolveZone(tz));
}

const R_UNIVERSAL_ZONE = /^(?:(?:Etc\/)?(?:UTC|GMT)|[+-]\d{2}(?::?\d{2})?)$/i;

/**
 * @param {AnyDateValue} value
 * @returns {string}
 */
export function toISO(value) {
    if (isDateValue(value)) {
        return value.toString();
    }
    const iso = value.toString({
        fractionalSecondDigits: 3,
        timeZoneName: "never",
        calendarName: "never",
    });
    if (value.offsetNanoseconds === 0 && R_UNIVERSAL_ZONE.test(value.timeZoneId)) {
        return `${iso.slice(0, -"+00:00".length)}Z`;
    }
    return iso;
}

/**
 * @param {AnyDateValue} value
 * @returns {string}
 */
export function toISODate(value) {
    return toDate(value).toString();
}

/** @type {Set<string>} */
const TIME_UNITS = new Set(["hour", "minute", "second"]);

/**
 * @param {DateTimeValue} value
 * @param {DateUnit} unit
 * @returns {DateTimeValue}
 */
function startOfDateTime(value, unit) {
    switch (unit) {
        case "year":
            return value.with({ month: 1, day: 1 }).startOfDay();
        case "quarter":
            return value
                .with({ month: value.month - ((value.month - 1) % 3), day: 1 })
                .startOfDay();
        case "month":
            return value.with({ day: 1 }).startOfDay();
        case "week":
            return value.subtract({ days: value.dayOfWeek - 1 }).startOfDay();
        case "day":
            return value.startOfDay();
        case "hour":
            return value.round({ smallestUnit: "hour", roundingMode: "floor" });
        case "minute":
            return value.round({ smallestUnit: "minute", roundingMode: "floor" });
        case "second":
            return value.round({ smallestUnit: "second", roundingMode: "floor" });
    }
    throw new Error(`startOf: unknown unit ${unit}`);
}

/**
 * @param {DateValue} value
 * @param {DateUnit} unit
 */
function assertDateUnit(value, unit) {
    if (TIME_UNITS.has(unit)) {
        throw new RangeError(`a date has no ${unit}: ${value}`);
    }
}

/**
 * @template {AnyDateValue} T
 * @param {T} value
 * @param {DateUnit} unit
 * @returns {T}
 */
export function startOf(value, unit) {
    if (isDateValue(value)) {
        assertDateUnit(value, unit);
        return /** @type {T} */ (
            startOfDateTime(atUTCMidnight(value), unit).toPlainDate()
        );
    }
    return /** @type {T} */ (
        startOfDateTime(/** @type {DateTimeValue} */ (value), unit)
    );
}

/**
 * @template {AnyDateValue} T
 * @param {T} value
 * @param {DateUnit} unit
 * @returns {T}
 */
export function endOf(value, unit) {
    if (isDateValue(value)) {
        assertDateUnit(value, unit);
        return /** @type {T} */ (endOf(atUTCMidnight(value), unit).toPlainDate());
    }
    const start = startOfDateTime(/** @type {DateTimeValue} */ (value), unit);
    const next =
        unit === "quarter" ? start.add({ months: 3 }) : start.add({ [`${unit}s`]: 1 });
    const end = TIME_UNITS.has(unit) ? next : next.startOfDay();
    return /** @type {T} */ (end.subtract({ milliseconds: 1 }));
}

/**
 * @param {AnyDateValue} a
 * @param {AnyDateValue} b
 * @param {DateUnit} unit
 * @returns {boolean}
 */
export function hasSame(a, b, unit) {
    assertSameKind(a, b, "hasSame");
    if (isDateValue(a)) {
        return startOf(a, unit).equals(startOf(/** @type {DateValue} */ (b), unit));
    }
    return startOfDateTime(a, unit).equals(
        startOfDateTime(
            /** @type {DateTimeValue} */ (b).withTimeZone(a.timeZoneId),
            unit,
        ),
    );
}

/**
 * @param {AnyDateValue} a
 * @param {AnyDateValue} b
 * @param {DiffUnit} unit
 * @returns {number}
 */
function diffValues(a, b, unit) {
    assertSameKind(a, b, "diff");
    return isDateValue(a)
        ? diff(atUTCMidnight(a), atUTCMidnight(/** @type {DateValue} */ (b)), unit)
        : diff(a, /** @type {DateTimeValue} */ (b), unit);
}

/**
 * @template {AnyDateValue} T
 * @param {T} value
 * @param {number} weekday
 * @returns {T}
 */
export function withWeekday(value, weekday) {
    return /** @type {T} */ (value.add({ days: weekday - value.dayOfWeek }));
}

/**
 * @template {AnyDateValue} T
 * @param {T | Date} value
 * @returns {{ year: number, week: number, startDate: T }}
 */
export function getLocalYearAndWeek(value) {
    if (isDateValue(value)) {
        const result = getLocalYearAndWeek(atUTCMidnight(value));
        return {
            ...result,
            startDate: /** @type {T} */ (result.startDate.toPlainDate()),
        };
    }
    const date = /** @type {DateTimeValue} */ (
        value instanceof Date ? fromJSDate(value) : value
    );
    const { weekStart } = localization;
    const startDate = date.subtract({ days: (date.dayOfWeek + 7 - weekStart) % 7 });
    let weekEnd =
        weekStart > 1 && weekStart < 5
            ? startDate.subtract({ days: (startDate.dayOfWeek + 6) % 7 })
            : startDate.add({ days: (8 - startDate.dayOfWeek) % 7 });
    weekEnd = weekEnd.add({ days: 6 });
    const jan4 = dateTime({ year: weekEnd.year, month: 1, day: 4 }, weekEnd.timeZoneId);
    let diffDays, year;
    if (compareDates(weekEnd, jan4) < 0) {
        diffDays = diff(weekEnd, jan4.subtract({ years: 1 }), "days");
        year = weekEnd.year - 1;
    } else {
        diffDays = diff(weekEnd, jan4, "days");
        year = weekEnd.year;
    }
    return {
        year,
        week: Math.trunc(diffDays / 7) + 1,
        startDate: /** @type {T} */ (/** @type {unknown} */ (startDate)),
    };
}

/**
 * @template {AnyDateValue} T
 * @param {T} date
 * @returns {T}
 */
export function getStartOfLocalWeek(date) {
    const { weekStart } = localization;
    const weekday = date.dayOfWeek < weekStart ? weekStart - 7 : weekStart;
    const start = withWeekday(date, weekday);
    return /** @type {T} */ (isDateValue(start) ? start : start.startOfDay());
}

/**
 * @template {AnyDateValue} T
 * @param {T} date
 * @returns {T}
 */
export function getEndOfLocalWeek(date) {
    return endOf(/** @type {T} */ (getStartOfLocalWeek(date).add({ days: 6 })), "day");
}

export { dateSettings, diffValues as diff, userTimeZone };
