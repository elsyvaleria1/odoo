// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { mockDate, mockTimeZone } from "@odoo/hoot-mock";
import {
    areDatesEqual,
    clampDate,
    compareDates,
    dateTime,
    diff,
    endOf,
    getEndOfLocalWeek,
    getLocalYearAndWeek,
    getStartOfLocalWeek,
    hasSame,
    isDateOrDateTimeValue,
    isDateTimeValue,
    isDateValue,
    isInRange,
    now,
    parseISO,
    startOf,
    toDate,
    toDateTime,
    today,
    toISO,
    toISODate,
    toJSDate,
    withWeekday,
} from "@web/core/l10n/date_utils";
import { localization } from "@web/core/l10n/localization";

/** @param {string} text */
const iso = (text) => /** @type {Temporal.ZonedDateTime} */ (parseISO(text));

describe.current.tags("headless");

/**
 * @param {number} weekStart
 * @param {() => void} fn
 */
function withWeekStart(weekStart, fn) {
    const had = Object.hasOwn(localization, "weekStart");
    const previous = had ? localization.weekStart : undefined;
    localization.weekStart = weekStart;
    try {
        fn();
    } finally {
        if (had) {
            localization.weekStart = previous;
        } else {
            delete (/** @type {any} */ (localization).weekStart);
        }
    }
}

describe("getLocalYearAndWeek", () => {
    test("weekStart=1 reproduces ISO-8601 numbering, 2015-2030", () => {
        let checked = 0;
        const mismatches = [];
        withWeekStart(1, () => {
            for (let year = 2015; year <= 2030; year++) {
                const days = [
                    ...[0, 1, 2, 3, 4, 5, 6].map((d) =>
                        dateTime({ year, month: 1, day: 1 }).add({ days: d }),
                    ),
                    ...[6, 5, 4, 3, 2, 1, 0].map((d) =>
                        dateTime({ year, month: 12, day: 31 }).subtract({ days: d }),
                    ),
                    ...Array.from({ length: 12 }, (_, m) =>
                        dateTime({ year, month: m + 1, day: 15 }),
                    ),
                ];
                for (const date of days) {
                    checked++;
                    const { year: gotYear, week } = getLocalYearAndWeek(date);
                    if (week !== date.weekOfYear || gotYear !== date.yearOfWeek) {
                        mismatches.push(
                            `${toISODate(date)}: got w${week}/${gotYear}, ISO w${date.weekOfYear}/${date.yearOfWeek}`,
                        );
                    }
                }
            }
        });
        expect(mismatches).toEqual([]);
        expect(checked).toBe(416);
    });

    test("startDate is always the first day of the LOCAL week", () => {
        for (const weekStart of [1, 2, 3, 4, 5, 6, 7]) {
            withWeekStart(weekStart, () => {
                for (let offset = 0; offset < 7; offset++) {
                    const date = dateTime({ year: 2026, month: 7, day: 27 }).add({
                        days: offset,
                    });
                    const { startDate } = getLocalYearAndWeek(date);
                    expect(startDate.dayOfWeek).toBe(weekStart, {
                        message: `weekStart=${weekStart}, date=${toISODate(date)}`,
                    });
                    const back = diff(date, startDate, "days");
                    expect(back >= 0 && back < 7).toBe(true, {
                        message: `weekStart=${weekStart}, date=${toISODate(date)}, startDate=${toISODate(startDate)}`,
                    });
                }
            });
        }
    });

    test("the number follows the ISO week the local week most overlaps", () => {
        const byWeekStart = {};
        for (const weekStart of [1, 2, 3, 4, 5, 6, 7]) {
            withWeekStart(weekStart, () => {
                byWeekStart[weekStart] = getLocalYearAndWeek(
                    dateTime({ year: 2026, month: 7, day: 29 }),
                ).week;
            });
        }
        expect(byWeekStart).toEqual({
            1: 31,
            2: 31,
            3: 31,
            4: 30,
            5: 31,
            6: 31,
            7: 31,
        });
    });

    test("year rolls over with the week, not with the calendar", () => {
        const seen = {};
        for (const weekStart of [1, 2, 5, 7]) {
            withWeekStart(weekStart, () => {
                const { year, week } = getLocalYearAndWeek(
                    dateTime({ year: 2025, month: 12, day: 29 }),
                );
                seen[weekStart] = `${week}/${year}`;
            });
        }
        expect(seen).toEqual({ 1: "1/2026", 2: "52/2025", 5: "1/2026", 7: "1/2026" });
    });

    test("accepts a plain JS Date as well as a Temporal date", () => {
        withWeekStart(1, () => {
            const date = dateTime({ year: 2026, month: 7, day: 29 });
            const fromJs = getLocalYearAndWeek(toJSDate(date));
            const fromTemporal = getLocalYearAndWeek(date);
            expect(fromJs.week).toBe(fromTemporal.week);
            expect(fromJs.year).toBe(fromTemporal.year);
            expect(toISODate(fromJs.startDate)).toBe(toISODate(fromTemporal.startDate));
        });
    });
});

describe("isInRange", () => {
    test("single DateTime value", () => {
        /** @type {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} */
        const range = [iso("2024-01-01T10:20:00Z"), iso("2024-01-01T10:40:00Z")];
        expect(isInRange(iso("2024-01-01T10:30:00Z"), range)).toBe(true);
        expect(isInRange(iso("2024-01-01T12:00:00Z"), range)).toBe(false);
    });

    test("falsy value or range", () => {
        /** @type {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} */
        const range = [iso("2024-01-01T10:20:00Z"), iso("2024-01-01T10:40:00Z")];
        expect(isInRange(null, range)).toBe(false);
        expect(isInRange(now(), null)).toBe(false);
    });

    test("array with a single truthy value falls back to single-value check", () => {
        /** @type {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} */
        const range = [iso("2024-01-01T10:20:00Z"), iso("2024-01-01T10:40:00Z")];
        expect(isInRange([iso("2024-01-01T10:30:00Z"), null], range)).toBe(true);
        expect(isInRange([null, iso("2024-01-01T12:00:00Z")], range)).toBe(false);
    });

    test("sorts a mixed-offset array chronologically, not by ISO string", () => {
        const earlier = /** @type {Temporal.ZonedDateTime} */ (
            parseISO("2024-01-01T10:00:00", "UTC")
        );
        const later = /** @type {Temporal.ZonedDateTime} */ (
            parseISO("2024-01-01T11:00:00", "UTC")
        ).withTimeZone("-10:00");
        /** @type {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} */
        const insideRange = [iso("2024-01-01T10:20:00Z"), iso("2024-01-01T10:40:00Z")];
        /** @type {[Temporal.ZonedDateTime, Temporal.ZonedDateTime]} */
        const outsideRange = [iso("2024-01-01T12:00:00Z"), iso("2024-01-01T13:00:00Z")];
        expect(isInRange([later, earlier], insideRange)).toBe(true);
        expect(isInRange([earlier, later], insideRange)).toBe(true);
        expect(isInRange([later, earlier], outsideRange)).toBe(false);
    });
});

describe("toISO", () => {
    test("ends in Z for a fixed zone at offset zero, not for a named zone at +00:00", () => {
        const fields = { year: 2019, month: 7, day: 14, hour: 9, minute: 30 };
        expect(toISO(iso("2019-07-14T09:30:00Z").withTimeZone("UTC"))).toBe(
            "2019-07-14T09:30:00.000Z",
        );
        expect(toISO(dateTime(fields, "UTC"))).toBe("2019-07-14T09:30:00.000Z");
        expect(toISO(dateTime(fields, "Etc/UTC"))).toBe("2019-07-14T09:30:00.000Z");
        expect(toISO(dateTime(fields, "Etc/GMT"))).toBe("2019-07-14T09:30:00.000Z");
        expect(toISO(dateTime(fields, "+00:00"))).toBe("2019-07-14T09:30:00.000Z");
        expect(toISO(dateTime({ ...fields, month: 1 }, "Europe/London"))).toBe(
            "2019-01-14T09:30:00.000+00:00",
        );
        expect(toISO(dateTime(fields, "Europe/London"))).toBe(
            "2019-07-14T09:30:00.000+01:00",
        );
        expect(toISO(dateTime(fields, "+05:30"))).toBe("2019-07-14T09:30:00.000+05:30");
    });
});

describe("dateTime", () => {
    test("fields above the largest given are now's, those below it their minimum", () => {
        mockDate("2023-04-25 11:37:30", 0);
        const fields = (/** @type {Parameters<typeof dateTime>[0]} */ given) =>
            toISO(dateTime(given, "UTC"));
        expect(fields({ year: 2020 })).toBe("2020-01-01T00:00:00.000Z");
        expect(fields({ day: 20, hour: 8, minute: 45 })).toBe(
            "2023-04-20T08:45:00.000Z",
        );
        expect(fields({ month: 5, day: 29 })).toBe("2023-05-29T00:00:00.000Z");
        expect(fields({ hour: 9, minute: 30 })).toBe("2023-04-25T09:30:00.000Z");
        expect(fields({}).slice(0, 19)).toBe("2023-04-25T11:37:30", {
            message: "the clock runs on after mockDate: the milliseconds may move",
        });
        expect(() => dateTime({ year: 2023, month: 2, day: 30 })).toThrow(RangeError);
    });
});

describe("dates are PlainDate", () => {
    /** @param {string} text */
    const day = (text) => Temporal.PlainDate.from(text);

    test("today is the day in the given zone, not a midnight", () => {
        mockDate("2024-02-29 23:30:00", 0);
        expect(today()).toBeInstanceOf(Temporal.PlainDate);
        expect(today("UTC").toString()).toBe("2024-02-29");
        expect(today("+05:00").toString()).toBe("2024-03-01");
        expect(today("-11:00").toString()).toBe("2024-02-29");
    });

    test("the predicates tell a date from a datetime", () => {
        const date = day("2024-02-29");
        const instant = dateTime({ year: 2024, month: 2, day: 29 }, "UTC");
        expect([isDateValue(date), isDateTimeValue(date)]).toEqual([true, false]);
        expect([isDateValue(instant), isDateTimeValue(instant)]).toEqual([false, true]);
        expect([isDateOrDateTimeValue(date), isDateOrDateTimeValue(instant)]).toEqual([
            true,
            true,
        ]);
        expect(isDateOrDateTimeValue("2024-02-29")).toBe(false);
    });

    test("a date and a datetime do not compare implicitly", () => {
        const date = day("2024-02-29");
        const instant = dateTime({ year: 2024, month: 2, day: 29 }, "UTC");
        expect(() => compareDates(date, instant)).toThrow(TypeError);
        expect(() => hasSame(instant, date, "day")).toThrow(TypeError);
        expect(() => diff(date, instant, "days")).toThrow(TypeError);
        expect(areDatesEqual(date, instant)).toBe(false);
    });

    test("dates compare, clamp and range as days", () => {
        expect(compareDates(day("2024-02-28"), day("2024-02-29"))).toBeLessThan(0);
        expect(areDatesEqual(day("2024-02-29"), day("2024-02-29"))).toBe(true);
        expect(
            clampDate(
                day("2024-03-15"),
                day("2024-02-01"),
                day("2024-02-29"),
            ).toString(),
        ).toBe("2024-02-29");
        expect(
            isInRange(day("2024-02-29"), [day("2024-02-29"), day("2024-03-01")]),
        ).toBe(true);
        expect(
            isInRange(day("2024-03-02"), [day("2024-02-29"), day("2024-03-01")]),
        ).toBe(false);
    });

    test("startOf and endOf keep a date a date: the first and last day", () => {
        const leap = day("2024-02-14");
        expect(startOf(leap, "year").toString()).toBe("2024-01-01");
        expect(startOf(leap, "quarter").toString()).toBe("2024-01-01");
        expect(startOf(leap, "month").toString()).toBe("2024-02-01");
        expect(startOf(leap, "week").toString()).toBe("2024-02-12");
        expect(startOf(leap, "day").toString()).toBe("2024-02-14");
        expect(endOf(leap, "year").toString()).toBe("2024-12-31");
        expect(endOf(leap, "quarter").toString()).toBe("2024-03-31");
        expect(endOf(leap, "month").toString()).toBe("2024-02-29");
        expect(endOf(leap, "week").toString()).toBe("2024-02-18");
        expect(endOf(leap, "day").toString()).toBe("2024-02-14");
        expect(() => startOf(leap, "hour")).toThrow(RangeError);
        expect(() => endOf(leap, "minute")).toThrow(RangeError);
    });

    test("hasSame and diff count calendar days, whatever the user's zone", () => {
        for (const offset of [-11, 0, +13]) {
            mockTimeZone(offset);
            expect(hasSame(day("2024-02-29"), day("2024-02-01"), "month")).toBe(true);
            expect(hasSame(day("2024-02-29"), day("2024-03-01"), "month")).toBe(false);
            expect(diff(day("2024-03-01"), day("2024-02-28"), "days")).toBe(2);
            expect(diff(day("2024-02-28"), day("2024-03-01"), "days")).toBe(-2);
            expect(diff(day("2024-03-31"), day("2024-03-01"), "weeks")).toBe(30 / 7);
            expect(diff(day("2025-02-28"), day("2024-02-29"), "years")).toBe(1);
        }
    });

    test("week helpers keep a date a date", () => {
        withWeekStart(7, () => {
            const date = day("2024-02-29");
            expect(getStartOfLocalWeek(date).toString()).toBe("2024-02-25");
            expect(getEndOfLocalWeek(date).toString()).toBe("2024-03-02");
            const { year, week, startDate } = getLocalYearAndWeek(date);
            expect([year, week, startDate.toString()]).toEqual([2024, 9, "2024-02-25"]);
            expect(withWeekday(date, 1).toString()).toBe("2024-02-26");
        });
    });

    test("toDateTime and toDate convert explicitly", () => {
        mockTimeZone(+5.5);
        const date = day("2024-02-29");
        expect(toISO(toDateTime(date))).toBe("2024-02-29T00:00:00.000+05:30");
        expect(toISO(toDateTime(date, "UTC"))).toBe("2024-02-29T00:00:00.000Z");
        const instant = dateTime({ year: 2024, month: 2, day: 29, hour: 22 }, "UTC");
        expect(toISO(toDateTime(instant))).toBe("2024-03-01T03:30:00.000+05:30");
        expect(toDate(instant).toString()).toBe("2024-02-29");
        expect(toDate(toDateTime(instant)).toString()).toBe("2024-03-01");
        expect(toDate(date)).toBe(date);
    });

    test("a date's ISO forms and JS Date", () => {
        mockTimeZone(-6);
        const date = day("2024-02-29");
        expect(toISO(date)).toBe("2024-02-29");
        expect(toISODate(date)).toBe("2024-02-29");
        expect(toJSDate(date).toISOString()).toBe("2024-02-29T06:00:00.000Z");
    });
});
