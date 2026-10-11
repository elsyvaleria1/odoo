/** @odoo-module native */
// @ts-check

import { constants, EvaluationError, helpers, registries } from "@odoo/o-spreadsheet";
import { formatWithTokens } from "@web/core/l10n/date_format";
import {
    deserializeDate,
    deserializeDateTime,
    today,
    toISODate,
    withWeekday,
} from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";

const { pivotTimeAdapterRegistry } = registries;
const { toNumber, toJsDate, toString } = helpers;
const { DEFAULT_LOCALE } = constants;

function boundedOdooNumberDateAdapter(lower, upper) {
    return {
        normalizeServerValue(groupBy, field, readGroupResult) {
            return Number(readGroupResult[groupBy]);
        },
        increment(normalizedValue, step) {
            const value = normalizedValue + step;
            if (value < lower || upper < value) {
                return undefined;
            }
            return value;
        },
    };
}

const odooDayAdapter = {
    normalizeServerValue(groupBy, field, readGroupResult) {
        const serverDayValue = getGroupStartingDay(field, groupBy, readGroupResult);
        return toNumber(serverDayValue, DEFAULT_LOCALE);
    },
    increment(normalizedValue, step) {
        return normalizedValue + step;
    },
};

const weekInputRegex = /\d{1,2}\/\d{4}/;

const odooWeekAdapter = {
    normalizeFunctionValue(value) {
        if (!weekInputRegex.test(value)) {
            const example = `"52/${today().year}"`;
            throw new EvaluationError(
                _t(
                    "Week value must be a string in the format %(example)s, but received %(received_value)s instead.",
                    { example, received_value: value },
                ),
            );
        }
        const [week, year] = toString(value).split("/");
        return `${Number(week)}/${Number(year)}`;
    },
    toValueAndFormat(normalizedValue, locale) {
        const [week, year] = normalizedValue.split("/");
        return {
            value: _t("W%(week)s %(year)s", { week, year }),
        };
    },
    toFunctionValue(normalizedValue) {
        return `"${normalizedValue}"`;
    },
    normalizeServerValue(groupBy, field, readGroupResult) {
        const weekValue = readGroupResult[groupBy];
        const { week, year } = parseServerWeekHeader(weekValue);
        return `${week}/${year}`;
    },
    increment(normalizedValue, step) {
        const [week, year] = normalizedValue.split("/");
        const weekNumber = Number(week);
        const yearNumber = Number(year);
        const firstWeek = withWeekday(
            Temporal.PlainDate.from({ year: yearNumber, month: 1, day: 4 }),
            1,
        );
        const nextWeek = firstWeek.add({ weeks: weekNumber - 1 + step });
        return `${nextWeek.weekOfYear}/${nextWeek.yearOfWeek}`;
    },
};

const odooMonthAdapter = {
    normalizeServerValue(groupBy, field, readGroupResult) {
        const firstOfTheMonth = getGroupStartingDay(field, groupBy, readGroupResult);
        return formatMonth(deserializeDate(firstOfTheMonth));
    },
    increment(normalizedValue, step) {
        const [month, year] = normalizedValue.split("/").map(Number);
        return formatMonth(
            Temporal.PlainDate.from({ year, month, day: 1 }).add({ months: step }),
        );
    },
};

/**
 * @param {Temporal.PlainDate} date
 * @returns {string}
 */
function formatMonth(date) {
    return formatWithTokens(date, "MM/yyyy", { numberingSystem: "latn" });
}

const NORMALIZED_QUARTER_REGEXP = /^[1-4]\/\d{4}$/;

const odooQuarterAdapter = {
    normalizeFunctionValue(value) {
        if (typeof value === "string" && NORMALIZED_QUARTER_REGEXP.test(value)) {
            return value;
        }
        const dateTime = toJsDate(value, DEFAULT_LOCALE);
        return `${dateTime.getQuarter()}/${dateTime.getFullYear()}`;
    },
    toValueAndFormat(normalizedValue) {
        const [quarter, year] = normalizedValue.split("/");
        return {
            value: _t("Q%(quarter)s %(year)s", { quarter, year }),
        };
    },
    toFunctionValue(normalizedValue) {
        return `"${normalizedValue}"`;
    },
    normalizeServerValue(groupBy, field, readGroupResult) {
        const firstOfTheQuarter = getGroupStartingDay(field, groupBy, readGroupResult);
        const date = deserializeDate(firstOfTheQuarter);
        return `${Math.ceil(date.month / 3)}/${date.year}`;
    },
    increment(normalizedValue, step) {
        const [quarter, year] = normalizedValue.split("/");
        const date = Temporal.PlainDate.from({
            year: Number(year),
            month: Number(quarter) * 3,
            day: 1,
        });
        const nextQuarter = date.add({ months: 3 * step });
        return `${Math.ceil(nextQuarter.month / 3)}/${nextQuarter.year}`;
    },
};

const odooYearAdapter = {
    normalizeServerValue(groupBy, field, readGroupResult) {
        const value = readGroupResult[groupBy];
        return Array.isArray(value) ? Number(value[1]) : false;
    },
    increment(normalizedValue, step) {
        return normalizedValue + step;
    },
};

const odooDayOfWeekAdapter = {
    normalizeServerValue(groupBy, field, readGroupResult, locale) {
        const fromLocaleIsZero =
            (7 - locale.weekStart + Number(readGroupResult[groupBy])) % 7;
        return fromLocaleIsZero + 1;
    },
    increment(normalizedValue, step) {
        return ((((normalizedValue - 1 + step) % 7) + 7) % 7) + 1;
    },
};

const odooHourNumberAdapter = {
    normalizeServerValue(groupBy, field, readGroupResult) {
        return Number(readGroupResult[groupBy]);
    },
    increment(normalizedValue, step) {
        return (((normalizedValue + step) % 24) + 24) % 24;
    },
};
const odooMinuteNumberAdapter = {
    normalizeServerValue(groupBy, field, readGroupResult) {
        return Number(readGroupResult[groupBy]);
    },
    increment(normalizedValue, step) {
        return (((normalizedValue + step) % 60) + 60) % 60;
    },
};
const odooSecondNumberAdapter = {
    normalizeServerValue(groupBy, field, readGroupResult) {
        return Number(readGroupResult[groupBy]);
    },
    increment(normalizedValue, step) {
        return (((normalizedValue + step) % 60) + 60) % 60;
    },
};

function falseHandlerDecorator(adapter) {
    return {
        normalizeServerValue(groupBy, field, readGroupResult, locale) {
            if (readGroupResult[groupBy] === false) {
                return false;
            }
            return adapter.normalizeServerValue(
                groupBy,
                field,
                readGroupResult,
                locale,
            );
        },
        increment(normalizedValue, step) {
            if (
                normalizedValue === false ||
                (typeof normalizedValue === "string" &&
                    normalizedValue.toLowerCase() === "false")
            ) {
                return false;
            }
            return adapter.increment(normalizedValue, step);
        },
        normalizeFunctionValue(value) {
            if (
                (typeof value === "string" && value.toLowerCase() === "false") ||
                value === false
            ) {
                return false;
            }
            return adapter.normalizeFunctionValue(value);
        },
        toValueAndFormat(normalizedValue, locale) {
            if (
                normalizedValue === false ||
                (typeof normalizedValue === "string" &&
                    normalizedValue.toLowerCase() === "false")
            ) {
                return { value: _t("None") };
            }
            return adapter.toValueAndFormat(normalizedValue, locale);
        },
        toFunctionValue(value) {
            if (value === false) {
                return "FALSE";
            }
            return adapter.toFunctionValue(value);
        },
    };
}

function extendSpreadsheetAdapter(granularity, adapter) {
    const originalAdapter = pivotTimeAdapterRegistry.get(granularity);
    pivotTimeAdapterRegistry.replace(
        granularity,
        falseHandlerDecorator({
            ...originalAdapter,
            ...adapter,
        }),
    );
}

pivotTimeAdapterRegistry.add("week", falseHandlerDecorator(odooWeekAdapter));
pivotTimeAdapterRegistry.add("quarter", falseHandlerDecorator(odooQuarterAdapter));

extendSpreadsheetAdapter("day", odooDayAdapter);
extendSpreadsheetAdapter("year", odooYearAdapter);
extendSpreadsheetAdapter("day_of_month", boundedOdooNumberDateAdapter(1, 31));
extendSpreadsheetAdapter("iso_week_number", boundedOdooNumberDateAdapter(0, 54));
extendSpreadsheetAdapter("month_number", boundedOdooNumberDateAdapter(1, 12));
extendSpreadsheetAdapter("quarter_number", boundedOdooNumberDateAdapter(1, 4));
extendSpreadsheetAdapter("day_of_week", odooDayOfWeekAdapter);
extendSpreadsheetAdapter("hour_number", odooHourNumberAdapter);
extendSpreadsheetAdapter("minute_number", odooMinuteNumberAdapter);
extendSpreadsheetAdapter("second_number", odooSecondNumberAdapter);
extendSpreadsheetAdapter("month", odooMonthAdapter);

/**
 * When grouping by a time field, return
 * the group starting day (local to the timezone)
 * @param {import("@spreadsheet").OdooField} field
 * @param {string} groupBy
 * @param {Record<string, any>} group
 * @returns {string | undefined}
 */
function getGroupStartingDay(field, groupBy, group) {
    const sqlValue = group[groupBy][0];
    if (field.type === "date") {
        return sqlValue;
    }
    return toISODate(deserializeDateTime(sqlValue, { tz: user.tz }));
}

/**
 * Parses a pivot week header value.
 * @param {Array} value
 * @example
 * parseServerWeekHeader(['2016-04-11', 'W15 2016']) // { week: 15, year: 2016 }
 */
function parseServerWeekHeader(value) {
    const [week, year] = value[1].split(" ");
    return { week: Number(week.slice(1)), year: Number(year) };
}
