// @ts-check
/** @odoo-module native */

import { dateSettings } from "./date_settings.js";

/**
 * @typedef {Temporal.ZonedDateTime | Temporal.PlainDateTime | Temporal.PlainDate} DateValue
 * @typedef {{ locale?: string, numberingSystem?: string }} FormatOptions
 */

export const DATE_SHORT = Object.freeze({
    year: "numeric",
    month: "numeric",
    day: "numeric",
});
export const DATE_MED = Object.freeze({
    year: "numeric",
    month: "short",
    day: "numeric",
});
export const DATE_MED_WITH_WEEKDAY = Object.freeze({
    year: "numeric",
    month: "short",
    day: "numeric",
    weekday: "short",
});
export const DATE_FULL = Object.freeze({
    year: "numeric",
    month: "long",
    day: "numeric",
});
export const DATE_HUGE = Object.freeze({
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
});
export const TIME_SIMPLE = Object.freeze({ hour: "numeric", minute: "numeric" });
export const TIME_WITH_SECONDS = Object.freeze({
    hour: "numeric",
    minute: "numeric",
    second: "numeric",
});
export const TIME_24_SIMPLE = Object.freeze({
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
});
export const TIME_24_WITH_SECONDS = Object.freeze({
    hour: "numeric",
    minute: "numeric",
    second: "numeric",
    hourCycle: "h23",
});
export const DATETIME_SHORT = Object.freeze({ ...DATE_SHORT, ...TIME_SIMPLE });
export const DATETIME_SHORT_WITH_SECONDS = Object.freeze({
    ...DATE_SHORT,
    ...TIME_WITH_SECONDS,
});
export const DATETIME_MED = Object.freeze({ ...DATE_MED, ...TIME_SIMPLE });
export const DATETIME_MED_WITH_SECONDS = Object.freeze({
    ...DATE_MED,
    ...TIME_WITH_SECONDS,
});
export const DATETIME_MED_WITH_WEEKDAY = Object.freeze({
    ...DATE_MED_WITH_WEEKDAY,
    ...TIME_SIMPLE,
});
export const DATETIME_FULL = Object.freeze({
    ...DATE_FULL,
    ...TIME_SIMPLE,
    timeZoneName: "short",
});
export const DATETIME_HUGE = Object.freeze({
    ...DATE_HUGE,
    ...TIME_SIMPLE,
    timeZoneName: "long",
});

/** @type {Record<string, Intl.DateTimeFormatOptions>} */
const MACROS = {
    D: DATE_SHORT,
    DD: DATE_MED,
    DDD: DATE_FULL,
    DDDD: DATE_HUGE,
    t: TIME_SIMPLE,
    tt: TIME_WITH_SECONDS,
    ttt: { ...TIME_WITH_SECONDS, timeZoneName: "short" },
    tttt: { ...TIME_WITH_SECONDS, timeZoneName: "long" },
    T: TIME_24_SIMPLE,
    TT: TIME_24_WITH_SECONDS,
    TTT: { ...TIME_24_WITH_SECONDS, timeZoneName: "short" },
    TTTT: { ...TIME_24_WITH_SECONDS, timeZoneName: "long" },
    f: DATETIME_SHORT,
    ff: DATETIME_MED,
    fff: DATETIME_FULL,
    ffff: DATETIME_HUGE,
    F: DATETIME_SHORT_WITH_SECONDS,
    FF: DATETIME_MED_WITH_SECONDS,
    FFF: { ...DATETIME_MED_WITH_SECONDS, month: "long", timeZoneName: "short" },
    FFFF: { ...DATE_HUGE, ...TIME_WITH_SECONDS, timeZoneName: "long" },
};

/** @type {Record<number, "short" | "long" | "narrow">} */
const NAME_LENGTH = { 3: "short", 4: "long", 5: "narrow" };

/** @type {Record<string, number>} */
const DIGIT_ZEROS = {
    arab: 0x660,
    arabext: 0x6f0,
    bali: 0x1b50,
    beng: 0x9e6,
    deva: 0x966,
    fullwide: 0xff10,
    gujr: 0xae6,
    guru: 0xa66,
    khmr: 0x17e0,
    knda: 0xce6,
    laoo: 0xed0,
    limb: 0x1946,
    mlym: 0xd66,
    mong: 0x1810,
    mymr: 0x1040,
    orya: 0xb66,
    tamldec: 0xbe6,
    telu: 0xc66,
    thai: 0xe50,
    tibt: 0xf20,
};

/** @type {Map<string, Intl.DateTimeFormat>} */
const formatters = new Map();

/**
 * @param {string | undefined} locale
 * @param {Intl.DateTimeFormatOptions} options
 * @returns {Intl.DateTimeFormat}
 */
function getFormatter(locale, options) {
    const key = `${locale}|${JSON.stringify(options)}`;
    let formatter = formatters.get(key);
    if (!formatter) {
        formatter = new Intl.DateTimeFormat(locale, options);
        formatters.set(key, formatter);
    }
    return formatter;
}

/** @param {DateValue} value */
function hasTime(value) {
    return !(value instanceof Temporal.PlainDate);
}

/**
 * @param {DateValue} value
 * @returns {{ date: Date, timeZone: string }}
 */
function toIntlInput(value) {
    if (value instanceof Temporal.ZonedDateTime) {
        return { date: new Date(value.epochMilliseconds), timeZone: value.timeZoneId };
    }
    const plain = value instanceof Temporal.PlainDate ? value.toPlainDateTime() : value;
    return {
        date: new Date(plain.toZonedDateTime("UTC").epochMilliseconds),
        timeZone: "UTC",
    };
}

/**
 * @param {DateValue} value
 * @param {Intl.DateTimeFormatOptions} options
 * @param {FormatOptions} [formatOptions]
 * @returns {Intl.DateTimeFormatPart[]}
 */
function formatParts(value, options, formatOptions = {}) {
    const { date, timeZone } = toIntlInput(value);
    const numberingSystem = formatOptions.numberingSystem;
    return getFormatter(formatOptions.locale, {
        ...options,
        timeZone,
        ...(numberingSystem ? { numberingSystem } : {}),
    }).formatToParts(date);
}

/**
 * @param {DateValue} value
 * @param {Intl.DateTimeFormatOptions} options
 * @param {FormatOptions} [formatOptions]
 * @returns {string}
 */
export function formatLocalized(value, options, formatOptions = {}) {
    return formatParts(value, options, formatOptions)
        .map((part) => part.value)
        .join("");
}

/**
 * @param {DateValue} value
 * @param {Intl.DateTimeFormatOptions} options
 * @param {Intl.DateTimeFormatPartTypes} type
 * @param {FormatOptions} formatOptions
 */
function extractPart(value, options, type, formatOptions) {
    return formatParts(value, options, formatOptions).find((part) => part.type === type)
        ?.value;
}

/**
 * @param {number} number
 * @param {number} width
 * @param {string | undefined} numberingSystem
 */
function formatNumber(number, width, numberingSystem) {
    const sign = number < 0 ? "-" : "";
    const digits = String(Math.abs(number)).padStart(width, "0");
    const zero = numberingSystem && DIGIT_ZEROS[numberingSystem];
    if (!zero) {
        return sign + digits;
    }
    return (
        sign +
        digits.replace(/\d/g, (digit) => String.fromCodePoint(zero + Number(digit)))
    );
}

/**
 * @param {string} format
 * @returns {{ literal: boolean, value: string }[]}
 */
export function tokenize(format) {
    /** @type {{ literal: boolean, value: string }[]} */
    const tokens = [];
    let index = 0;
    while (index < format.length) {
        const char = format[index];
        if (char === "'") {
            const end = format.indexOf("'", index + 1);
            if (end === index + 1) {
                tokens.push({ literal: true, value: "'" });
                index += 2;
                continue;
            }
            const stop = end === -1 ? format.length : end;
            tokens.push({ literal: true, value: format.slice(index + 1, stop) });
            index = stop + 1;
            continue;
        }
        if (/[a-z]/i.test(char)) {
            let end = index + 1;
            while (format[end] === char) {
                end++;
            }
            tokens.push({ literal: false, value: format.slice(index, end) });
            index = end;
            continue;
        }
        tokens.push({ literal: true, value: char });
        index++;
    }
    return tokens;
}

/**
 * @param {DateValue} value
 * @returns {string}
 */
function offsetOf(value) {
    return value instanceof Temporal.ZonedDateTime ? value.offset : "+00:00";
}

/**
 * @param {DateValue} value
 * @param {string} token
 * @param {FormatOptions} options
 * @returns {string}
 */
function formatToken(value, token, options) {
    const ns = options.numberingSystem;
    const time = hasTime(value)
        ? /** @type {Temporal.ZonedDateTime | Temporal.PlainDateTime} */ (value)
        : null;
    const letter = token[0];
    const length = token.length;
    if (MACROS[token]) {
        return formatLocalized(value, MACROS[token], options);
    }
    switch (letter) {
        case "S":
            return formatNumber(time?.millisecond ?? 0, length === 3 ? 3 : 1, ns);
        case "s":
            return formatNumber(time?.second ?? 0, length, ns);
        case "m":
            return formatNumber(time?.minute ?? 0, length, ns);
        case "H":
            return formatNumber(time?.hour ?? 0, length, ns);
        case "h":
            return formatNumber((((time?.hour ?? 0) + 11) % 12) + 1, length, ns);
        case "a":
            return (
                extractPart(
                    value,
                    { hour: "numeric", hourCycle: "h12" },
                    "dayPeriod",
                    options,
                ) ?? ((time?.hour ?? 0) < 12 ? "AM" : "PM")
            );
        case "d":
            return formatNumber(value.day, length, ns);
        case "c":
        case "E":
            if (length <= 2) {
                return formatNumber(value.dayOfWeek, 1, ns);
            }
            return /** @type {string} */ (
                extractPart(
                    value,
                    letter === "c"
                        ? { weekday: NAME_LENGTH[/** @type {3|4|5} */ (length)] }
                        : {
                              weekday: NAME_LENGTH[/** @type {3|4|5} */ (length)],
                              month: "long",
                              day: "numeric",
                          },
                    "weekday",
                    options,
                )
            );
        case "L":
        case "M":
            if (length <= 2) {
                return formatNumber(value.month, length, ns);
            }
            return /** @type {string} */ (
                extractPart(
                    value,
                    letter === "L"
                        ? { month: NAME_LENGTH[/** @type {3|4|5} */ (length)] }
                        : {
                              month: NAME_LENGTH[/** @type {3|4|5} */ (length)],
                              day: "numeric",
                          },
                    "month",
                    options,
                )
            );
        case "y":
            if (length === 2) {
                return formatNumber(value.year % 100, 2, ns);
            }
            return formatNumber(value.year, length === 1 ? 1 : length, ns);
        case "q":
            return formatNumber(Math.ceil(value.month / 3), length, ns);
        case "o":
            return formatNumber(value.dayOfYear, length, ns);
        case "W":
            return formatNumber(/** @type {number} */ (value.weekOfYear), length, ns);
        case "k":
            return formatNumber(
                length === 2
                    ? /** @type {number} */ (value.yearOfWeek) % 100
                    : /** @type {number} */ (value.yearOfWeek),
                length,
                ns,
            );
        case "G":
            return (
                extractPart(
                    value,
                    { era: length === 1 ? "short" : length === 2 ? "long" : "narrow" },
                    "era",
                    options,
                ) ?? ""
            );
        case "Z": {
            const offset = offsetOf(value);
            if (length === 1) {
                const [hours, minutes] = offset.slice(1).split(":").map(Number);
                return `${offset[0]}${hours}${minutes ? `:${String(minutes).padStart(2, "0")}` : ""}`;
            }
            if (length === 2) {
                return offset;
            }
            if (length === 3) {
                return offset.replace(":", "");
            }
            return (
                extractPart(
                    value,
                    { timeZoneName: length === 4 ? "short" : "long" },
                    "timeZoneName",
                    options,
                ) ?? offset
            );
        }
        case "z":
            return value instanceof Temporal.ZonedDateTime ? value.timeZoneId : "UTC";
        case "X":
            return formatNumber(
                Math.floor(toIntlInput(value).date.getTime() / 1000),
                1,
                ns,
            );
        case "x":
            return formatNumber(toIntlInput(value).date.getTime(), 1, ns);
        default:
            return token;
    }
}

/**
 * @param {DateValue} value
 * @param {string} format
 * @param {FormatOptions} [options]
 * @returns {string}
 */
export function formatWithTokens(value, format, options = {}) {
    return tokenize(format)
        .map((token) =>
            token.literal ? token.value : formatToken(value, token.value, options),
        )
        .join("");
}

/**
 * @param {string} text
 * @returns {string}
 */
export function toLatinDigits(text) {
    return text.replace(/\p{Nd}/gu, (char) => {
        const code = /** @type {number} */ (char.codePointAt(0));
        for (const zero of Object.values(DIGIT_ZEROS)) {
            if (code >= zero && code <= zero + 9) {
                return String(code - zero);
            }
        }
        return char;
    });
}

/** @param {string} text */
function escapeLiteral(text) {
    return text
        .split(/\s+/)
        .map((piece) => RegExp.escape(piece))
        .join("\\s+");
}

/** @param {string} name */
function normalizeName(name) {
    return name
        .replace(/\./g, "")
        .replace(/[ \u00a0]/g, " ")
        .toLowerCase();
}

/** @param {string[]} names */
function namesPattern(names) {
    return `(${names
        .map((name) =>
            name
                .split(/([. \u00a0])/)
                .map((part) =>
                    part === "."
                        ? "\\.?"
                        : part === " " || part === "\u00a0"
                          ? "[ \u00a0]"
                          : RegExp.escape(part),
                )
                .join(""),
        )
        .join("|")})`;
}

/** @type {Map<string, string[]>} */
const nameLists = new Map();

/**
 * @param {"month" | "weekday" | "dayPeriod"} kind
 * @param {"long" | "short" | "narrow" | ""} style
 * @param {boolean} standalone
 * @param {string | undefined} locale
 * @returns {string[]}
 */
function localNames(kind, style, standalone, locale) {
    const key = `${kind}|${style}|${standalone}|${locale}`;
    let names = nameLists.get(key);
    if (names) {
        return names;
    }
    names = [];
    const width = /** @type {"long" | "short" | "narrow"} */ (style || "long");
    if (kind === "month") {
        for (let month = 1; month <= 12; month++) {
            const value = Temporal.PlainDate.from({ year: 2009, month, day: 15 });
            names.push(
                /** @type {string} */ (
                    extractPart(
                        value,
                        standalone
                            ? { month: width }
                            : { month: width, day: "numeric" },
                        "month",
                        { locale },
                    )
                ),
            );
        }
    } else if (kind === "weekday") {
        for (let day = 1; day <= 7; day++) {
            const value = Temporal.PlainDate.from({ year: 2009, month: 6, day });
            names.push(
                /** @type {string} */ (
                    extractPart(
                        value,
                        standalone
                            ? { weekday: width }
                            : { weekday: width, month: "long", day: "numeric" },
                        "weekday",
                        { locale },
                    )
                ),
            );
        }
    } else {
        for (const hour of [9, 21]) {
            const value = Temporal.PlainDateTime.from({
                year: 2009,
                month: 6,
                day: 1,
                hour,
            });
            names.push(
                extractPart(value, { hour: "numeric", hourCycle: "h12" }, "dayPeriod", {
                    locale,
                }) ?? (hour < 12 ? "AM" : "PM"),
            );
        }
    }
    nameLists.set(key, names);
    return names;
}

/**
 * @param {"long" | "short" | "narrow"} [style]
 * @param {{ locale?: string, standalone?: boolean }} [options]
 * @returns {string[]}
 */
export function monthNames(style = "long", options = {}) {
    return [
        ...localNames(
            "month",
            style,
            options.standalone ?? true,
            options.locale ?? dateSettings.locale,
        ),
    ];
}

/**
 * @param {"long" | "short" | "narrow"} [style]
 * @param {{ locale?: string, standalone?: boolean }} [options]
 * @returns {string[]}
 */
export function weekdayNames(style = "long", options = {}) {
    return [
        ...localNames(
            "weekday",
            style,
            options.standalone ?? true,
            options.locale ?? dateSettings.locale,
        ),
    ];
}

/**
 * @param {{ locale?: string }} [options]
 * @returns {string[]}
 */
export function meridiemNames(options = {}) {
    return [
        ...localNames("dayPeriod", "", false, options.locale ?? dateSettings.locale),
    ];
}

/**
 * @typedef ParsedFields
 * @property {number} [year]
 * @property {number} [month]
 * @property {number} [day]
 * @property {number} [dayOfYear]
 * @property {number} [hour]
 * @property {number} [minute]
 * @property {number} [second]
 * @property {number} [millisecond]
 * @property {"am" | "pm"} [meridiem]
 */

/** @type {Record<string, string>} */
const NUMERIC_PATTERNS = {
    yyyy: "(\\d{4})",
    yyyyy: "(\\d{4,6})",
    yyyyyy: "(\\d{6})",
    yy: "(\\d{2})",
    y: "(\\d{1,6})",
    MM: "(\\d{2})",
    M: "(\\d{1,2})",
    LL: "(\\d{2})",
    L: "(\\d{1,2})",
    dd: "(\\d{2})",
    d: "(\\d{1,2})",
    HH: "(\\d{2})",
    H: "(\\d{1,2})",
    hh: "(\\d{2})",
    h: "(\\d{1,2})",
    mm: "(\\d{2})",
    m: "(\\d{1,2})",
    ss: "(\\d{2})",
    s: "(\\d{1,2})",
    SSS: "(\\d{3})",
    S: "(\\d{1,3})",
    ooo: "(\\d{3})",
    o: "(\\d{1,3})",
};

/**
 * @param {string} text
 * @param {string} format
 * @param {{ locale?: string, twoDigitCutoffYear?: number }} [options]
 * @returns {ParsedFields | null}
 */
export function parseWithTokens(text, format, options = {}) {
    const locale = options.locale;
    /** @type {((match: string, fields: ParsedFields) => boolean)[]} */
    const setters = [];
    let pattern = "";
    for (const token of tokenize(format)) {
        if (token.literal) {
            pattern += escapeLiteral(token.value);
            continue;
        }
        const value = token.value;
        const letter = value[0];
        const numeric = NUMERIC_PATTERNS[value];
        if (numeric) {
            pattern += numeric;
            setters.push((match, fields) => {
                const number = Number(match);
                switch (letter) {
                    case "y":
                        fields.year =
                            value.length === 2
                                ? number +
                                  (number > (options.twoDigitCutoffYear ?? 60)
                                      ? 1900
                                      : 2000)
                                : number;
                        return true;
                    case "M":
                    case "L":
                        fields.month = number;
                        return true;
                    case "d":
                        fields.day = number;
                        return true;
                    case "H":
                    case "h":
                        fields.hour = number;
                        return true;
                    case "m":
                        fields.minute = number;
                        return true;
                    case "s":
                        fields.second = number;
                        return true;
                    case "S":
                        fields.millisecond =
                            value.length === 3 ? number : Number(match.padEnd(3, "0"));
                        return true;
                    case "o":
                        fields.dayOfYear = number;
                        return true;
                }
                return false;
            });
            continue;
        }
        if (
            (letter === "M" || letter === "L") &&
            value.length >= 3 &&
            value.length <= 4
        ) {
            const names = localNames(
                "month",
                NAME_LENGTH[/** @type {3|4} */ (value.length)],
                letter === "L",
                locale,
            );
            pattern += namesPattern(names);
            const normalized = names.map(normalizeName);
            setters.push((match, fields) => {
                fields.month = normalized.indexOf(normalizeName(match)) + 1;
                return fields.month > 0;
            });
            continue;
        }
        if (
            (letter === "c" || letter === "E") &&
            value.length >= 3 &&
            value.length <= 4
        ) {
            const names = localNames(
                "weekday",
                NAME_LENGTH[/** @type {3|4} */ (value.length)],
                letter === "c",
                locale,
            );
            pattern += namesPattern(names);
            setters.push(() => true);
            continue;
        }
        if (letter === "a") {
            const names = localNames("dayPeriod", "", false, locale);
            pattern += namesPattern(names);
            const normalized = names.map(normalizeName);
            setters.push((match, fields) => {
                fields.meridiem =
                    normalized.indexOf(normalizeName(match)) === 0 ? "am" : "pm";
                return true;
            });
            continue;
        }
        return null;
    }
    const match = new RegExp(`^${pattern}$`, "iu").exec(text);
    if (!match) {
        return null;
    }
    /** @type {ParsedFields} */
    const fields = {};
    for (let index = 0; index < setters.length; index++) {
        if (!setters[index](match[index + 1], fields)) {
            return null;
        }
    }
    if (fields.meridiem && fields.hour !== undefined) {
        if (fields.hour < 1 || fields.hour > 12) {
            return null;
        }
        fields.hour = (fields.hour % 12) + (fields.meridiem === "pm" ? 12 : 0);
    }
    return fields;
}
