// @ts-check
/** @odoo-module native */

import { parseSQL, resolveZone } from "./date_utils.js";

/** @type {WeakMap<Temporal.ZonedDateTime, string>} */
const dateTimeCache = new WeakMap();

/** @param {number} number */
const pad2 = (number) => String(number).padStart(2, "0");

/**
 * @param {Temporal.ZonedDateTime | Temporal.PlainDateTime} value
 * @returns {string}
 */
function formatServerDateTime(value) {
    return (
        `${String(value.year).padStart(4, "0")}-${pad2(value.month)}-${pad2(value.day)} ` +
        `${pad2(value.hour)}:${pad2(value.minute)}:${pad2(value.second)}`
    );
}

/**
 * The server's date format, "YYYY-MM-DD": a date's own day, or the day a
 * datetime falls on in its zone.
 *
 * @param {Temporal.PlainDate | Temporal.ZonedDateTime | null | false | undefined} value
 * @returns {string|false}
 */
export function serializeDate(value) {
    if (!value) {
        return false;
    }
    return value instanceof Temporal.PlainDate
        ? value.toString()
        : value.toPlainDate().toString();
}

/**
 * The server's datetime format, "YYYY-MM-DD HH:MM:SS" in UTC.
 *
 * @param {Temporal.ZonedDateTime | null | false | undefined} value
 * @returns {string|false}
 */
export function serializeDateTime(value) {
    if (!value) {
        return false;
    }
    let serialized = dateTimeCache.get(value);
    if (serialized === undefined) {
        serialized = formatServerDateTime(value.withTimeZone("UTC"));
        dateTimeCache.set(value, serialized);
    }
    return serialized;
}

/**
 * @param {string} value
 * @param {Temporal.ZonedDateTime | null} parsed
 * @returns {Temporal.ZonedDateTime}
 */
function ensureParsed(value, parsed) {
    if (!parsed) {
        throw new RangeError(`not a server date or datetime: ${JSON.stringify(value)}`);
    }
    return parsed;
}

/**
 * @param {unknown} value
 * @param {string} zone
 * @returns {Temporal.ZonedDateTime | null}
 */
function readServerValue(value, zone) {
    return typeof value === "string" ? parseSQL(value.trim(), zone) : null;
}

/**
 * A server date, "YYYY-MM-DD", as that day. Read with luxon's fromSQL grammar,
 * as before; a time, when present, is dropped: a date has none.
 *
 * @param {string} value
 * @returns {Temporal.PlainDate}
 */
export function deserializeDate(value) {
    return ensureParsed(value, readServerValue(value, "UTC")).toPlainDate();
}

/**
 * A server datetime, "YYYY-MM-DD HH:MM:SS" in UTC, in `tz` (the user's zone
 * by default). Read with luxon's fromSQL grammar, as before: fractional
 * seconds, surrounding white space and an explicit offset or "Z" are accepted.
 *
 * @param {string} value
 * @param {{tz?: string}} [options]
 * @returns {Temporal.ZonedDateTime}
 */
export function deserializeDateTime(value, options = {}) {
    return ensureParsed(value, readServerValue(value, "UTC")).withTimeZone(
        resolveZone(options?.tz),
    );
}
