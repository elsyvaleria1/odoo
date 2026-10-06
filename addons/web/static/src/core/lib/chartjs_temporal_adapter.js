// @ts-check
/** @odoo-module native */

import { formatLocalized, formatWithTokens } from "@web/core/l10n/date_format";
import {
    dateSettings,
    DATETIME_MED_WITH_SECONDS,
    endOf,
    fromEpochMilliseconds,
    fromJSDate,
    isDateOrDateTimeValue,
    now,
    parseFormatted,
    parseISO,
    resolveZone,
    startOf,
    TIME_SIMPLE,
    TIME_WITH_SECONDS,
    toDateTime,
} from "@web/core/l10n/dates";

/**
 * @typedef {{ zone?: string, locale?: string, numberingSystem?: string }} AdapterOptions
 * @typedef {"millisecond" | "second" | "minute" | "hour" | "day" | "week" | "month" | "quarter" | "year"} TimeUnit
 */

const FORMATS = {
    datetime: DATETIME_MED_WITH_SECONDS,
    millisecond: "h:mm:ss.SSS a",
    second: TIME_WITH_SECONDS,
    minute: TIME_SIMPLE,
    hour: { hour: "numeric" },
    day: { day: "numeric", month: "short" },
    week: "DD",
    month: { month: "short", year: "numeric" },
    quarter: "'Q'q - yyyy",
    year: { year: "numeric" },
};

const MS_PER_DAY = 24 * 3600 * 1000;

/**
 * Milliseconds per unit as time scales have always measured a difference: a
 * fixed length, where a month is 30 days, a quarter 91 and a year 365.
 *
 * @type {Record<TimeUnit, number>}
 */
const CASUAL_UNIT_MS = {
    millisecond: 1,
    second: 1000,
    minute: 60 * 1000,
    hour: 3600 * 1000,
    day: MS_PER_DAY,
    week: 7 * MS_PER_DAY,
    month: 30 * MS_PER_DAY,
    quarter: 91 * MS_PER_DAY,
    year: 365 * MS_PER_DAY,
};

const OBJECT_UNITS = /** @type {const} */ ([
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
    "millisecond",
]);

/**
 * @param {Record<string, number>} fields
 * @param {string} zone
 * @returns {Temporal.ZonedDateTime | null}
 */
function fromFields(fields, zone) {
    const current = now(zone);
    const largest = OBJECT_UNITS.findIndex((unit) => fields[unit] !== undefined);
    /** @type {Record<string, number>} */
    const values = {};
    for (const [index, unit] of OBJECT_UNITS.entries()) {
        if (fields[unit] !== undefined) {
            values[unit] = fields[unit];
        } else if (index < largest) {
            values[unit] = current[unit];
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
 * Installs the Temporal date adapter onto a Chart.js module's `_adapters`, so
 * that time-scale axes read, step and label dates as the rest of the web client.
 *
 * @param {any} adapters the `_adapters` export of chart.js
 */
export function installChartDateAdapter(adapters) {
    adapters._date.override({
        _id: "temporal",

        /**
         * @this {{ options: AdapterOptions }}
         * @param {number} time
         * @returns {Temporal.ZonedDateTime}
         */
        _create(time) {
            return fromEpochMilliseconds(time, resolveZone(this.options.zone));
        },

        /**
         * @this {{ options: AdapterOptions }}
         * @param {{ locale?: string }} chartOptions
         */
        init(chartOptions) {
            if (!this.options.locale) {
                this.options.locale = chartOptions.locale;
            }
        },

        formats() {
            return FORMATS;
        },

        /**
         * @this {{ options: AdapterOptions, _create(time: number): Temporal.ZonedDateTime }}
         * @param {unknown} value
         * @param {unknown} [format]
         * @returns {number | null}
         */
        parse(value, format) {
            if (value === null || value === undefined) {
                return null;
            }
            const zone = resolveZone(this.options.zone);
            /** @type {Temporal.ZonedDateTime | null} */
            let date = null;
            try {
                if (typeof value === "number") {
                    date = this._create(value);
                } else if (typeof value === "string") {
                    date =
                        typeof format === "string"
                            ? parseFormatted(value, format, zone)
                            : parseISO(value, zone);
                } else if (value instanceof Date) {
                    date = fromJSDate(value, zone);
                } else if (isDateOrDateTimeValue(value)) {
                    date = toDateTime(value, zone);
                } else if (typeof value === "object") {
                    date = fromFields(
                        /** @type {Record<string, number>} */ (value),
                        zone,
                    );
                }
            } catch {
                return null;
            }
            return date ? date.epochMilliseconds : null;
        },

        /**
         * @this {{ options: AdapterOptions, _create(time: number): Temporal.ZonedDateTime }}
         * @param {number} time
         * @param {string | Intl.DateTimeFormatOptions} format
         * @returns {string}
         */
        format(time, format) {
            const date = this._create(time);
            const formatOptions = {
                locale: this.options.locale ?? dateSettings.locale,
                numberingSystem:
                    this.options.numberingSystem ?? dateSettings.numberingSystem,
            };
            return typeof format === "string"
                ? formatWithTokens(date, format, formatOptions)
                : formatLocalized(date, format, formatOptions);
        },

        /**
         * @this {{ _create(time: number): Temporal.ZonedDateTime }}
         * @param {number} time
         * @param {number} amount
         * @param {TimeUnit} unit
         * @returns {number}
         */
        add(time, amount, unit) {
            const duration =
                unit === "quarter" ? { months: amount * 3 } : { [`${unit}s`]: amount };
            return this._create(time).add(duration).epochMilliseconds;
        },

        /**
         * @param {number} max
         * @param {number} min
         * @param {TimeUnit} unit
         * @returns {number}
         */
        diff(max, min, unit) {
            return (max - min) / CASUAL_UNIT_MS[unit];
        },

        /**
         * @this {{ _create(time: number): Temporal.ZonedDateTime }}
         * @param {number} time
         * @param {TimeUnit | "isoWeek"} unit
         * @param {number} [weekday]
         * @returns {number}
         */
        startOf(time, unit, weekday) {
            if (unit === "isoWeek") {
                const isoWeekday = Math.trunc(Math.min(Math.max(0, weekday ?? 0), 6));
                const date = this._create(time);
                return date
                    .subtract({ days: (date.dayOfWeek - isoWeekday + 7) % 7 })
                    .startOfDay().epochMilliseconds;
            }
            if (!unit || unit === "millisecond") {
                return time;
            }
            return startOf(this._create(time), unit).epochMilliseconds;
        },

        /**
         * @this {{ _create(time: number): Temporal.ZonedDateTime }}
         * @param {number} time
         * @param {TimeUnit} unit
         * @returns {number}
         */
        endOf(time, unit) {
            if (unit === "millisecond") {
                return time;
            }
            return endOf(this._create(time), unit).epochMilliseconds;
        },
    });
}
