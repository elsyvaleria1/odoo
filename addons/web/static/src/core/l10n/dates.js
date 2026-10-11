// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { localization } from "@web/core/l10n/localization";
import { _t } from "@web/core/translation";
import { memoize } from "@web/core/utils/functions";

import {
    DATE_MED,
    DATETIME_MED_WITH_SECONDS,
    formatLocalized,
    formatWithTokens,
    parseWithTokens,
    toLatinDigits,
} from "./date_format.js";
import { dateSettings } from "./date_settings.js";
import {
    compareDates,
    dateTime,
    diff,
    endOf,
    hasSame,
    isDateValue,
    isInRange,
    now,
    parseISO,
    resolveZone,
    startOf,
    toDateTime,
    today,
} from "./date_utils.js";

export {
    DATE_FULL,
    DATE_HUGE,
    DATE_MED,
    DATE_MED_WITH_WEEKDAY,
    DATE_SHORT,
    DATETIME_FULL,
    DATETIME_HUGE,
    DATETIME_MED,
    DATETIME_MED_WITH_SECONDS,
    DATETIME_MED_WITH_WEEKDAY,
    DATETIME_SHORT,
    DATETIME_SHORT_WITH_SECONDS,
    meridiemNames,
    monthNames,
    TIME_24_SIMPLE,
    TIME_24_WITH_SECONDS,
    TIME_SIMPLE,
    TIME_WITH_SECONDS,
    weekdayNames,
} from "./date_format.js";
export {
    deserializeDate,
    deserializeDateTime,
    serializeDate,
    serializeDateTime,
} from "./date_serialization.js";
export {
    areDatesEqual,
    clampDate,
    compareDates,
    dateSettings,
    dateTime,
    diff,
    endOf,
    fromEpochMilliseconds,
    fromJSDate,
    getEndOfLocalWeek,
    getLocalYearAndWeek,
    getStartOfLocalWeek,
    hasSame,
    isDateOrDateTimeValue,
    isDateTimeValue,
    isDateValue,
    isInRange,
    maxDate,
    minDate,
    now,
    parseISO,
    parseSQL,
    resolveZone,
    startOf,
    toDate,
    toDateTime,
    today,
    toISO,
    toISODate,
    toJSDate,
    userTimeZone,
    withWeekday,
} from "./date_utils.js";

/**
 * @typedef ConversionOptions
 * @property {string} [format]
 * @property {string} [tz]
 * @typedef {[NullableDateTime, NullableDateTime]} NullableDateRange
 * @typedef {Temporal.ZonedDateTime | null | false} NullableDateTime
 * @typedef {Temporal.PlainDate | null | false} NullableDate
 * @typedef {Temporal.PlainDate | Temporal.ZonedDateTime | null | false} NullableDateValue
 */

/**
 * @typedef ConversionLocalOptions
 * @property {boolean} [showSeconds]
 * @property {boolean} [showTime]
 * @property {boolean} [showDate]
 * @property {string} [tz]
 */

/** @type {Temporal.ZonedDateTime | undefined} */
let minValidDate;
/** @type {Temporal.ZonedDateTime | undefined} */
let maxValidDate;
export function getMinValidDate() {
    return (minValidDate ??= dateTime({ year: 1000 }));
}
export function getMaxValidDate() {
    return (maxValidDate ??= endOf(dateTime({ year: 9999 }), "year"));
}

const log = makeLogger("web.l10n");

const nonAlphaRegex = /[^a-z]/gi;
const nonDigitRegex = /[^\d]/g;
const alphaCharRegex = /[a-z]/i;

/** @type {Record<string, string>} */
const normalizeFormatTable = {
    a: "ccc",
    A: "cccc",
    b: "MMM",
    B: "MMMM",
    d: "dd",
    H: "HH",
    I: "hh",
    j: "ooo",
    m: "MM",
    M: "mm",
    p: "a",
    S: "ss",
    y: "yy",
    Y: "yyyy",
    c: "ccc MMM d HH:mm:ss yyyy",
    x: "MM/dd/yy",
    X: "HH:mm:ss",
};

/** @type {Record<string, "days" | "months" | "weeks" | "years" | "hours" | "minutes" | "seconds">} */
const smartDateUnits = {
    d: "days",
    m: "months",
    w: "weeks",
    y: "years",
    H: "hours",
    M: "minutes",
    S: "seconds",
};
/** @type {Record<string, number>} */
const smartWeekdays = {
    monday: 1,
    tuesday: 2,
    wednesday: 3,
    thursday: 4,
    friday: 5,
    saturday: 6,
    sunday: 7,
};

export class ConversionError extends Error {
    name = "ConversionError";
}

/**
 * @param {NullableDateTime | undefined} date
 * @returns {date is Temporal.ZonedDateTime}
 */
function isValidDate(date) {
    return Boolean(date && isInRange(date, [getMinValidDate(), getMaxValidDate()]));
}

/**
 * `now` with its day, month or year set to `number`, the day kept within the
 * resulting month as the server's relativedelta keeps it: "=31d" in February is
 * its last day, not early March.
 *
 * @param {Temporal.ZonedDateTime} current
 * @param {"days" | "months" | "years"} unit
 * @param {number} number
 * @returns {Temporal.ZonedDateTime}
 */
function setSmartDatePart(current, unit, number) {
    const day = unit === "days" ? number : current.day;
    const month = current.with({
        day: 1,
        ...(unit === "months"
            ? { month: number }
            : unit === "years"
              ? { year: number }
              : {}),
    });
    const clamped = Math.min(day, month.daysInMonth);
    log.logic("smartDate:set", () => ({ unit, number, day, clamped }));
    return month.with({ day: clamped });
}

/** @type {Record<string, "hour" | "minute" | "second">} */
const SINGULAR_TIME_UNITS = { hours: "hour", minutes: "minute", seconds: "second" };

/**
 * @param {string} value
 * @param {string} zone the zone "today" and "now" are read in
 * @returns {NullableDateTime}
 */
function parseSmartDateInput(value, zone) {
    const terms = value.split(/\s+/);
    let current = startOf(now(zone), "second");
    if (terms[0] === "today") {
        terms.shift();
        current = current.startOfDay();
    } else if (terms[0] === "now") {
        terms.shift();
    } else if (terms.length === 1 && /^[=+-]\d+$/.test(terms[0])) {
        terms[0] += "d";
    }

    for (let i = 0; i < terms.length; i++) {
        const term = terms[i];
        const operator = term[0];
        if (term.length < 3 || !["+", "-", "="].includes(operator)) {
            return null;
        }

        const dayname = term.slice(1);
        if (Object.hasOwn(smartWeekdays, dayname) || dayname === "week_start") {
            const { weekStart } = localization;
            const weekdayNumber =
                dayname === "week_start" ? weekStart : smartWeekdays[dayname];
            let weekdayOffset =
                ((weekdayNumber - weekStart + 7) % 7) -
                ((current.dayOfWeek - weekStart + 7) % 7);
            if (operator === "+" || operator === "-") {
                if (weekdayOffset > 0 && operator === "-") {
                    weekdayOffset -= 7;
                } else if (weekdayOffset < 0 && operator === "+") {
                    weekdayOffset += 7;
                }
            } else {
                current = current.startOfDay();
            }
            current = current.add({ days: weekdayOffset });
            continue;
        }

        try {
            const fieldName = smartDateUnits[/** @type {string} */ (term.at(-1))];
            const number = Number.parseInt(term.slice(1, -1), 10);
            if (!fieldName || Number.isNaN(number)) {
                return null;
            }
            if (operator === "+") {
                current = current.add({ [fieldName]: number });
            } else if (operator === "-") {
                current = current.subtract({ [fieldName]: number });
            } else if (operator === "=") {
                const timeUnit = SINGULAR_TIME_UNITS[fieldName];
                if (timeUnit) {
                    current = startOf(current, timeUnit).with({ [timeUnit]: number });
                } else if (fieldName === "weeks") {
                    return null;
                } else {
                    current = setSmartDatePart(
                        current.startOfDay(),
                        /** @type {"days" | "months" | "years"} */ (fieldName),
                        number,
                    );
                }
            }
        } catch {
            return null;
        }
    }

    return current;
}

/** @type {(str: string) => string} */
const stripAlphaDupes = memoize(function stripAlphaDupes(str) {
    return str.replace(/[a-z]/gi, (letter, index, str) =>
        letter === str[index - 1] ? "" : letter,
    );
});

/**
 * A server strftime format ("%d/%m/%Y") in the token grammar the date layer
 * formats and parses with ("dd/MM/yyyy").
 *
 * @type {(format: string) => string}
 */
export const strftimeToDateFormat = memoize(function strftimeToDateFormat(format) {
    const output = [];
    let inToken = false;
    let noPadding = false;
    for (let index = 0; index < format.length; ++index) {
        let character = format[index];
        if (character === "%" && !inToken) {
            inToken = true;
            noPadding = false;
            continue;
        }
        if (inToken && character === "-") {
            noPadding = true;
            continue;
        }
        if (alphaCharRegex.test(character)) {
            if (inToken && normalizeFormatTable[character] !== undefined) {
                character = normalizeFormatTable[character];
                if (noPadding && /^(.)\1$/.test(character)) {
                    character = character[0];
                }
            } else {
                if (inToken) {
                    log.logic("strftime directive without date token", () => ({
                        directive: `%${character}`,
                        format,
                    }));
                }
                character = `'${character}'`;
            }
        }
        output.push(character);
        inToken = false;
        noPadding = false;
    }
    return output.join("");
});

const DATE_MED_NO_YEAR = { ...DATE_MED };
delete DATE_MED_NO_YEAR.year;
const DATETIME_MED_NO_SECONDS = { ...DATETIME_MED_WITH_SECONDS };
delete DATETIME_MED_NO_SECONDS.second;

/** @type {number} */
let currentYear;
let currentYearDayStart = 0;
let currentYearDayEnd = 0;
function getCurrentYear() {
    const nowMs = Date.now();
    if (nowMs < currentYearDayStart || nowMs >= currentYearDayEnd) {
        const startOfToday = now().startOfDay();
        currentYear = startOfToday.year;
        currentYearDayStart = startOfToday.epochMilliseconds;
        currentYearDayEnd = startOfToday.add({ days: 1 }).epochMilliseconds;
    }
    return currentYear;
}

/** @returns {import("./date_format.js").FormatOptions} */
function formatOptions() {
    return {
        locale: dateSettings.locale,
        numberingSystem: dateSettings.numberingSystem,
    };
}

/**
 * `value` through a token `format` ("dd/MM/yyyy") in the user's locale and
 * numbering system: what luxon's toFormat did.
 *
 * @param {Temporal.ZonedDateTime | Temporal.PlainDate | Temporal.PlainDateTime} value
 * @param {string} format
 * @returns {string}
 */
export function formatValue(value, format) {
    return formatWithTokens(value, format, formatOptions());
}

/**
 * `value` for Intl `options` (a preset such as DATE_MED) in the user's locale
 * and numbering system: what luxon's toLocaleString did.
 *
 * @param {Temporal.ZonedDateTime | Temporal.PlainDate | Temporal.PlainDateTime} value
 * @param {Intl.DateTimeFormatOptions} options
 * @returns {string}
 */
export function toLocaleString(value, options) {
    return formatLocalized(value, options, formatOptions());
}

/** @param {"auto" | "always"} numeric */
function relativeTimeFormatter(numeric) {
    return new Intl.RelativeTimeFormat(
        dateSettings.locale,
        /** @type {Intl.RelativeTimeFormatOptions} */ ({
            numeric,
            numberingSystem: dateSettings.numberingSystem,
        }),
    );
}

/** @type {Array<"years" | "months" | "days" | "hours" | "minutes" | "seconds">} */
const RELATIVE_UNITS = ["years", "months", "days", "hours", "minutes", "seconds"];

/**
 * `value` relative to now in the largest unit it is at least one of ("in 2
 * hours", "3 days ago"), truncated toward zero: luxon's toRelative.
 *
 * A date is read as the start of its day in the user's zone.
 *
 * @param {Temporal.ZonedDateTime | Temporal.PlainDate} value
 * @returns {string}
 */
export function toRelative(value) {
    if (isDateValue(value)) {
        return toRelative(toDateTime(value));
    }
    const base = now(value.timeZoneId);
    const formatter = relativeTimeFormatter("always");
    for (const unit of RELATIVE_UNITS) {
        const count = diff(value, base, unit);
        if (Math.abs(count) >= 1) {
            return formatter.format(Math.trunc(count), unit);
        }
    }
    return formatter.format(compareDates(base, value) > 0 ? -0 : 0, "seconds");
}

/** @type {Array<["years" | "months" | "days", "year" | "month" | "day"]>} */
const RELATIVE_CALENDAR_UNITS = [
    ["years", "year"],
    ["months", "month"],
    ["days", "day"],
];

/**
 * `value` against the current day in calendar units counted between the
 * starts of the units holding each ("tomorrow", "last month"): luxon's
 * toRelativeCalendar.
 *
 * @param {Temporal.ZonedDateTime | Temporal.PlainDate} value
 * @param {"years" | "months" | "days"} [unit]
 * @returns {string}
 */
export function toRelativeCalendar(value, unit) {
    const base = isDateValue(value) ? today() : now(value.timeZoneId);
    const formatter = relativeTimeFormatter("auto");
    const units = unit
        ? RELATIVE_CALENDAR_UNITS.filter(([plural]) => plural === unit)
        : RELATIVE_CALENDAR_UNITS;
    for (const [plural, singular] of units) {
        const count = hasSame(value, base, singular)
            ? 0
            : Math.round(
                  diff(startOf(value, singular), startOf(base, singular), plural),
              );
        if (unit || Math.abs(count) >= 1) {
            return formatter.format(count, plural);
        }
    }
    return formatter.format(0, "days");
}

/**
 * @param {NullableDateValue | undefined} value
 * @param {ConversionOptions} [options={}]
 */
export function formatDate(value, options = {}) {
    if (!value) {
        return "";
    }
    return formatValue(value, options.format || localization.dateFormat);
}

/**
 * @param {NullableDateValue | undefined} value a date is the start of its day in `options.tz`
 * @param {ConversionOptions} [options={}]
 */
export function formatDateTime(value, options = {}) {
    if (!value) {
        return "";
    }
    const format = options.format || localization.dateTimeFormat;
    return formatValue(toDateTime(value, options.tz), format);
}

/** @param {NullableDateValue | undefined} value */
export function toLocaleDateString(value) {
    if (!value) {
        return "";
    }
    return toLocaleString(
        value,
        getCurrentYear() === value.year ? DATE_MED_NO_YEAR : DATE_MED,
    );
}

/**
 * @param {NullableDateValue | undefined} value a date is the start of its day in `options.tz`
 * @param {ConversionLocalOptions} [options]
 */
export function toLocaleDateTimeString(
    value,
    options = { showDate: true, showTime: true, showSeconds: false },
) {
    if (!value) {
        return "";
    }
    /** @type {Intl.DateTimeFormatOptions} */
    const format = options.showSeconds
        ? { ...DATETIME_MED_WITH_SECONDS }
        : { ...DATETIME_MED_NO_SECONDS };
    if (options.showDate === false) {
        delete format.day;
        delete format.month;
        delete format.year;
    }
    if (options.showTime === false) {
        delete format.hour;
        delete format.minute;
    }
    const shown = toDateTime(value, options.tz);
    if (getCurrentYear() === shown.year) {
        delete format.year;
    }
    return toLocaleString(shown, format);
}

/** @type {Map<string, Intl.NumberFormat>} */
const durationFormatters = new Map();

const CASUAL_SECONDS = {
    years: 365 * 86400,
    months: 30 * 86400,
    days: 86400,
    hours: 3600,
    minutes: 60,
};

/**
 * @param {number} seconds
 * @param {boolean} showFullDuration
 * @returns {string}
 */
export function formatDuration(seconds, showFullDuration) {
    const displayStyle = showFullDuration ? "long" : "narrow";
    const numberOfValuesToDisplay = showFullDuration ? 2 : 1;
    /** @type {Array<"years" | "months" | "days" | "hours" | "minutes">} */
    const durationKeys = ["years", "months", "days", "hours", "minutes"];
    const intlUnitByKey = {
        years: "year",
        months: "month",
        days: "day",
        hours: "hour",
        minutes: "minute",
    };

    const sign = seconds < 0 ? -1 : 1;
    let magnitude = Math.abs(Math.trunc(seconds));
    magnitude -= magnitude % 60;

    const locale = dateSettings.locale || undefined;

    /**
     * @param {number} value
     * @param {"years" | "months" | "days" | "hours" | "minutes"} key
     * @returns {string}
     */
    const formatUnit = (value, key) => {
        const cacheKey = `${locale}|${key}|${displayStyle}`;
        let formatter = durationFormatters.get(cacheKey);
        if (!formatter) {
            formatter = new Intl.NumberFormat(locale, {
                style: "unit",
                unit: intlUnitByKey[key],
                unitDisplay: displayStyle,
            });
            durationFormatters.set(cacheKey, formatter);
        }
        let formatted = formatter.format(value);
        if (!showFullDuration && key === "months" && (locale || "").includes("en")) {
            formatted = formatted.replace(/m(?=\W*$)/, "M");
        }
        return formatted;
    };

    /** @type {Array<["years" | "months" | "days" | "hours" | "minutes", number]>} */
    const parts = [];
    let remaining = magnitude;
    for (const key of durationKeys) {
        const value = Math.floor(remaining / CASUAL_SECONDS[key]);
        remaining -= value * CASUAL_SECONDS[key];
        if (value) {
            parts.push([key, value]);
            if (parts.length >= numberOfValuesToDisplay) {
                break;
            }
        }
    }

    if (!parts.length) {
        return formatUnit(0, "minutes");
    }

    return parts
        .map(([key, value], index) =>
            formatUnit(index === 0 ? sign * value : value, key),
        )
        .join(", ");
}

const UNIT_ORDER = /** @type {const} */ ([
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
    "millisecond",
]);

/**
 * `text` read through a token `format` in `zone`, as luxon's fromFormat: units
 * above the largest one the format carries come from now, units below it are at
 * their minimum. Null when it does not match or spells an impossible date.
 *
 * @param {string} text
 * @param {string} format
 * @param {string} [tz]
 * @returns {Temporal.ZonedDateTime | null}
 */
export function parseFormatted(text, format, tz) {
    const fields = parseWithTokens(toLatinDigits(text), format, {
        locale: dateSettings.locale,
        twoDigitCutoffYear: dateSettings.twoDigitCutoffYear,
    });
    if (!fields) {
        return null;
    }
    const zone = resolveZone(tz);
    const current = now(zone);
    /** @type {Record<string, number>} */
    const values = {};
    if (fields.dayOfYear !== undefined) {
        const year = fields.year ?? current.year;
        try {
            const day = Temporal.PlainDate.from({ year, month: 1, day: 1 }).add({
                days: fields.dayOfYear - 1,
            });
            if (day.year !== year) {
                return null;
            }
            fields.month = day.month;
            fields.day = day.day;
            fields.year = year;
        } catch {
            return null;
        }
    }
    const given = /** @type {Record<string, number | undefined>} */ (fields);
    const largest = UNIT_ORDER.findIndex((unit) => given[unit] !== undefined);
    for (const [index, unit] of UNIT_ORDER.entries()) {
        const value = given[unit];
        if (value !== undefined) {
            values[unit] = value;
        } else if (index < largest) {
            values[unit] = /** @type {any} */ (current)[unit];
        } else {
            values[unit] = unit === "month" || unit === "day" ? 1 : 0;
        }
    }
    try {
        return Temporal.ZonedDateTime.from(
            { .../** @type {any} */ (values), timeZone: zone },
            { overflow: "reject" },
        );
    } catch {
        return null;
    }
}

/**
 * @param {string} value
 * @param {ConversionOptions} [options={}]
 * @returns {Temporal.PlainDate | null}
 * @throws {ConversionError}
 */
export function parseDate(value, options = {}) {
    const parsed = parseDateTime(value, {
        ...options,
        format: options.format || localization.dateFormat,
    });
    return parsed ? parsed.toPlainDate() : null;
}

/**
 * @param {string} value
 * @param {ConversionOptions} [options={}]
 * @returns {Temporal.ZonedDateTime | null}
 * @throws {ConversionError}
 */
export function parseDateTime(value, options = {}) {
    if (!value) {
        return null;
    }

    const fmt = options.format || localization.dateTimeFormat;
    const zone = resolveZone(options.tz);

    /** @type {NullableDateTime} */
    let result = parseFormatted(value, fmt, zone);

    if (!isValidDate(result)) {
        result = parseSmartDateInput(value, zone);
    }

    if (!isValidDate(result)) {
        result = parseFormatted(value, stripAlphaDupes(fmt), zone);
    }

    if (!isValidDate(result)) {
        const latin = toLatinDigits(value);
        const digitList = latin.split(nonDigitRegex).filter(Boolean);
        const fmtList = fmt.split(nonAlphaRegex).filter(Boolean);
        const valWoSeps = digitList.join("");

        let carry = 0;
        const fmtWoSeps = fmtList
            .map((part, i) => {
                const digitLength = (digitList[i] || "").length;
                const actualPart = part.slice(0, digitLength + carry);
                carry += digitLength - actualPart.length;
                return actualPart;
            })
            .join("");

        result = parseFormatted(valWoSeps, fmtWoSeps, zone);
    }

    if (!isValidDate(result)) {
        const latin = toLatinDigits(value);
        if (latin.replace(nonDigitRegex, "").length > 4) {
            result = parseISO(latin, zone);
        }
    }

    if (!isValidDate(result)) {
        throw new ConversionError(_t("'%s' is not a correct date or datetime", value));
    }

    return result.withTimeZone(zone);
}
