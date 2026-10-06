// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { tick } from "@odoo/hoot-dom";
import { Deferred } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import {
    dateSettings,
    dateTime,
    diff,
    parseISO,
    toISO,
    toISODate,
} from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { Time } from "@web/core/l10n/time";
import { KeepLast } from "@web/core/utils/concurrency";
import {
    computeCalendarRange,
    computeFiltersDomain,
    computeRangeDomain,
    delayHours,
} from "@web/views/calendar/calendar_date_range";
import { CalendarModel } from "@web/views/calendar/calendar_model";
import { normalizeCalendarRecord } from "@web/views/calendar/calendar_record";

function withWeekStart(weekStart, fn) {
    patchWithCleanup(localization, { weekStart });
    return fn();
}

describe("computeCalendarRange — day scale", () => {
    test("returns the full day containing the anchor date", () => {
        const date = parseISO("2024-01-15T14:30:00");

        const { start, end } = withWeekStart(1, () =>
            computeCalendarRange("day", date, false),
        );

        expect(start.day).toBe(15);
        expect(start.hour).toBe(0);
        expect(start.minute).toBe(0);
        expect(end.day).toBe(15);
        expect(end.hour).toBe(23);
        expect(end.minute).toBe(59);
    });
});

describe("computeCalendarRange — week scale, Monday start", () => {
    test("returns Mon–Sun when weekStart=1 (Monday) and anchor is a Wednesday", () => {
        const date = parseISO("2024-01-17");

        const { start, end } = withWeekStart(1, () =>
            computeCalendarRange("week", date, false),
        );

        expect(start.day).toBe(15);
        expect(start.month).toBe(1);
        expect(end.day).toBe(21);
        expect(end.month).toBe(1);
    });

    test("anchor on Monday itself is already the start of the week", () => {
        const date = parseISO("2024-01-15");

        const { start } = withWeekStart(1, () =>
            computeCalendarRange("week", date, false),
        );

        expect(start.day).toBe(15);
    });

    test("anchor on Sunday returns preceding Monday as start", () => {
        const date = parseISO("2024-01-21");

        const { start, end } = withWeekStart(1, () =>
            computeCalendarRange("week", date, false),
        );

        expect(start.day).toBe(15);
        expect(end.day).toBe(21);
    });
});

describe("computeCalendarRange — week scale, Sunday start", () => {
    test("returns Sun–Sat when weekStart=7 (Sunday) and anchor is a Wednesday", () => {
        const date = parseISO("2024-01-17");

        const { start, end } = withWeekStart(7, () =>
            computeCalendarRange("week", date, false),
        );

        expect(start.day).toBe(14);
        expect(end.day).toBe(20);
    });
});

describe("computeCalendarRange — month scale, no overflow", () => {
    test("returns startOf month to endOf month", () => {
        const date = parseISO("2024-01-17");

        const { start, end } = withWeekStart(1, () =>
            computeCalendarRange("month", date, false),
        );

        expect(start.day).toBe(1);
        expect(start.month).toBe(1);
        expect(end.day).toBe(31);
        expect(end.month).toBe(1);
    });
});

describe("computeCalendarRange — month scale, with overflow", () => {
    test("returns a 6-week range starting from the aligned first day of the first week", () => {
        const date = parseISO("2024-01-17");

        const { start, end } = withWeekStart(1, () =>
            computeCalendarRange("month", date, true),
        );

        expect(start.day).toBe(1);
        expect(start.month).toBe(1);
        expect(end.month).toBe(2);
        expect(end.day).toBe(11);
    });

    test("start aligns to the local week start when month begins mid-week", () => {
        const date = parseISO("2024-02-15");

        const { start } = withWeekStart(1, () =>
            computeCalendarRange("month", date, true),
        );

        expect(start.month).toBe(1);
        expect(start.day).toBe(29);
    });
});

describe("computeRangeDomain — with date_stop", () => {
    test("produces two-condition domain for events overlapping the range", () => {
        const range = {
            start: parseISO("2024-01-15"),
            end: parseISO("2024-01-21"),
        };

        const domain = computeRangeDomain(
            { date_start: "start_date", date_stop: "stop_date" },
            "date",
            range,
        );

        expect(domain.length).toBe(2);
        expect(domain[0][0]).toBe("start_date");
        expect(domain[0][1]).toBe("<=");
        expect(domain[1][0]).toBe("stop_date");
        expect(domain[1][1]).toBe(">=");
    });
});

describe("computeRangeDomain — without date_stop, without date_delay", () => {
    test("produces two-condition domain restricting date_start to the range", () => {
        const range = {
            start: parseISO("2024-01-15"),
            end: parseISO("2024-01-21"),
        };

        const domain = computeRangeDomain({ date_start: "start_date" }, "date", range);

        expect(domain.length).toBe(2);
        expect(domain[0][0]).toBe("start_date");
        expect(domain[0][1]).toBe("<=");
        expect(domain[1][0]).toBe("start_date");
        expect(domain[1][1]).toBe(">=");
    });
});

describe("computeRangeDomain — with date_delay (no date_stop)", () => {
    test("produces only an upper-bound condition when date_delay is present", () => {
        const range = {
            start: parseISO("2024-01-15"),
            end: parseISO("2024-01-21"),
        };

        const domain = computeRangeDomain(
            { date_start: "start_date", date_delay: "planned_hours" },
            "datetime",
            range,
        );

        expect(domain.length).toBe(1);
        expect(domain[0][0]).toBe("start_date");
        expect(domain[0][1]).toBe("<=");
    });

    test("a duration floor bounds date_start from below", () => {
        const range = {
            start: parseISO("2024-01-15T00:00:00", "UTC"),
            end: parseISO("2024-01-21T23:59:59", "UTC"),
        };

        const domain = computeRangeDomain(
            { date_start: "start_date", date_delay: "planned_hours" },
            "datetime",
            range,
            range.start.subtract({ hours: 36 }),
        );

        expect(domain).toEqual([
            ["start_date", "<=", "2024-01-21 23:59:59"],
            ["start_date", ">=", "2024-01-13 12:00:00"],
        ]);
    });

    test("a date start is floored to the day of the duration floor", () => {
        const range = {
            start: parseISO("2024-01-15"),
            end: parseISO("2024-01-21"),
        };

        const domain = computeRangeDomain(
            { date_start: "start_date", date_delay: "planned_hours" },
            "date",
            range,
            range.start.subtract({ hours: 1 }),
        );

        expect(domain[1]).toEqual(["start_date", ">=", "2024-01-14"]);
    });
});

describe("computeRangeDomain — serialization format", () => {
    test("date type serializes to YYYY-MM-DD strings", () => {
        const range = {
            start: parseISO("2024-01-15"),
            end: parseISO("2024-01-21"),
        };

        const domain = computeRangeDomain({ date_start: "start_date" }, "date", range);

        expect(typeof domain[0][2]).toBe("string");
        expect(domain[0][2]).toMatch(/^\d{4}-\d{2}-\d{2}/);
    });
});

describe("computeFiltersDomain — static filters (writeResModel)", () => {
    test("produces 'in' domain from active static filter values", () => {
        const filterSections = {
            user_id: {
                filters: [
                    { value: 1, active: true },
                    { value: 2, active: false },
                    { value: 3, active: true },
                ],
            },
        };
        const filtersInfo = {
            user_id: { writeResModel: "res.users" },
        };

        const domain = computeFiltersDomain(filterSections, filtersInfo);

        expect(domain.length).toBe(1);
        expect(domain[0][0]).toBe("user_id");
        expect(domain[0][1]).toBe("in");
        expect(domain[0][2]).toEqual([1, 3]);
    });

    test("produces 'in []' domain when no static filters are active (excludes all records)", () => {
        const filterSections = {
            user_id: { filters: [{ value: 1, active: false }] },
        };
        const filtersInfo = { user_id: { writeResModel: "res.users" } };

        const domain = computeFiltersDomain(filterSections, filtersInfo);

        expect(domain.length).toBe(1);
        expect(domain[0]).toEqual(["user_id", "in", []]);
    });
});

describe("computeFiltersDomain — dynamic filters (no writeResModel)", () => {
    test("produces 'not in' domain from inactive dynamic filter values", () => {
        const filterSections = {
            categ_id: {
                filters: [
                    { value: 10, active: true },
                    { value: 20, active: false },
                    { value: 30, active: false },
                ],
            },
        };
        const filtersInfo = {
            categ_id: {},
        };

        const domain = computeFiltersDomain(filterSections, filtersInfo);

        expect(domain.length).toBe(1);
        expect(domain[0][0]).toBe("categ_id");
        expect(domain[0][1]).toBe("not in");
        expect(domain[0][2]).toEqual([20, 30]);
    });

    test("produces no domain when all dynamic values are active", () => {
        const filterSections = {
            categ_id: { filters: [{ value: 1, active: true }] },
        };
        const filtersInfo = { categ_id: {} };

        const domain = computeFiltersDomain(filterSections, filtersInfo);

        expect(domain.length).toBe(0);
    });
});

describe("computeFiltersDomain — mixed static and dynamic", () => {
    test("produces separate clauses for each field", () => {
        const filterSections = {
            user_id: { filters: [{ value: 1, active: true }] },
            categ_id: { filters: [{ value: 10, active: false }] },
        };
        const filtersInfo = {
            user_id: { writeResModel: "res.users" },
            categ_id: {},
        };

        const domain = computeFiltersDomain(filterSections, filtersInfo);

        const fields = domain.map((d) => d[0]);
        expect(fields).toInclude("user_id");
        expect(fields).toInclude("categ_id");

        const userClause = domain.find((d) => d[0] === "user_id");
        const categClause = domain.find((d) => d[0] === "categ_id");
        expect(userClause[1]).toBe("in");
        expect(categClause[1]).toBe("not in");
    });
});

describe("normalizeCalendarRecord — datetime event (timed)", () => {
    test("extracts id, title, start/end DateTimes, and isAllDay=false", () => {
        const rawRecord = {
            id: 42,
            display_name: "Team Meeting",
            start_datetime: "2024-01-15 10:00:00",
            stop_datetime: "2024-01-15 11:00:00",
        };
        const fields = {
            start_datetime: { type: "datetime" },
            stop_datetime: { type: "datetime" },
        };
        const fieldMapping = {
            date_start: "start_datetime",
            date_stop: "stop_datetime",
        };

        const result = normalizeCalendarRecord(rawRecord, {
            fields,
            fieldMapping,
            isTimeHidden: false,
            scale: "week",
            isSmall: false,
        });

        expect(result.id).toBe(42);
        expect(result.title).toBe("Team Meeting");
        expect(result.isAllDay).toBe(false);
        expect(result.start.day).toBe(15);
        expect(result.end.day).toBe(15);
        expect(result.isMonth).toBe(false);
        expect(result.isSmall).toBe(false);
    });
});

describe("normalizeCalendarRecord — date event (all-day)", () => {
    test("sets isAllDay=true and isTimeHidden=true for date-type fields", () => {
        const rawRecord = {
            id: 1,
            display_name: "Holiday",
            start_date: "2024-01-15",
            stop_date: "2024-01-16",
        };
        const fields = {
            start_date: { type: "date" },
            stop_date: { type: "date" },
        };

        const result = normalizeCalendarRecord(rawRecord, {
            fields,
            fieldMapping: { date_start: "start_date", date_stop: "stop_date" },
            isTimeHidden: false,
            scale: "month",
            isSmall: false,
        });

        expect(result.isAllDay).toBe(true);
        expect(result.isTimeHidden).toBe(true);
        expect(result.isMonth).toBe(true);
    });
});

describe("normalizeCalendarRecord — all_day flag override", () => {
    test("sets isAllDay=true when all_day field is truthy on the record", () => {
        const rawRecord = {
            id: 1,
            display_name: "All Day Event",
            start_dt: "2024-01-15 00:00:00",
            is_all_day: true,
        };
        const fields = {
            start_dt: { type: "datetime" },
        };

        const result = normalizeCalendarRecord(rawRecord, {
            fields,
            fieldMapping: { date_start: "start_dt", all_day: "is_all_day" },
            isTimeHidden: false,
            scale: "day",
            isSmall: false,
        });

        expect(result.isAllDay).toBe(true);
    });
});

describe("normalizeCalendarRecord — color extraction", () => {
    test("uses numeric color value directly as colorIndex", () => {
        const rawRecord = {
            id: 1,
            display_name: "X",
            start_dt: "2024-01-15 10:00:00",
            color_value: 7,
        };
        const fields = { start_dt: { type: "datetime" } };

        const result = normalizeCalendarRecord(rawRecord, {
            fields,
            fieldMapping: { date_start: "start_dt", color: "color_value" },
            isTimeHidden: false,
            scale: "week",
            isSmall: false,
        });

        expect(result.colorIndex).toBe(7);
    });

    test("extracts id from many2one color value", () => {
        const rawRecord = {
            id: 1,
            display_name: "X",
            start_dt: "2024-01-15 10:00:00",
            color_field: [3, "Red Team"],
        };
        const fields = { start_dt: { type: "datetime" } };

        const result = normalizeCalendarRecord(rawRecord, {
            fields,
            fieldMapping: { date_start: "start_dt", color: "color_field" },
            isTimeHidden: false,
            scale: "week",
            isSmall: false,
        });

        expect(result.colorIndex).toBe(3);
    });
});

describe("delayHours — one reading of date_delay for drawing and the range floor", () => {
    test("a number is kept, a negative one is zero, anything else is the default hour", () => {
        expect(delayHours(2.5)).toBe(2.5);
        expect(delayHours(0)).toBe(0);
        expect(delayHours(-3)).toBe(0);
        expect(delayHours(false)).toBe(1);
        expect(delayHours(undefined)).toBe(1);
    });
});

describe("normalizeCalendarRecord — duration fallback", () => {
    test("uses duration=1 when date_delay field is absent", () => {
        const rawRecord = {
            id: 1,
            display_name: "X",
            start_dt: "2024-01-15 10:00:00",
        };
        const fields = { start_dt: { type: "datetime" } };

        const result = normalizeCalendarRecord(rawRecord, {
            fields,
            fieldMapping: { date_start: "start_dt" },
            isTimeHidden: false,
            scale: "week",
            isSmall: false,
        });

        expect(result.duration).toBe(1);
    });

    test("applies duration to compute end when no date_stop given", () => {
        const rawRecord = {
            id: 1,
            display_name: "X",
            start_dt: "2024-01-15 10:00:00",
            planned_hours: 3,
        };
        const fields = { start_dt: { type: "datetime" } };

        const result = normalizeCalendarRecord(rawRecord, {
            fields,
            fieldMapping: { date_start: "start_dt", date_delay: "planned_hours" },
            isTimeHidden: false,
            scale: "week",
            isSmall: false,
        });

        expect(diff(result.end, result.start, "hours")).toBe(3);
    });

    test("a zero date_delay ends the record where it starts", () => {
        const result = normalizeCalendarRecord(
            {
                id: 1,
                display_name: "X",
                start_dt: "2024-01-15 10:00:00",
                planned_hours: 0,
            },
            {
                fields: { start_dt: { type: "datetime" } },
                fieldMapping: { date_start: "start_dt", date_delay: "planned_hours" },
                isTimeHidden: false,
                scale: "week",
                isSmall: false,
            },
        );

        expect(result.duration).toBe(0);
        expect(result.end.epochMilliseconds).toBe(result.start.epochMilliseconds);
    });

    test("with a date_stop, the duration is the real length, whatever date_delay holds", () => {
        const options = {
            fields: {
                start_dt: { type: "datetime" },
                stop_dt: { type: "datetime" },
                is_all_day: { type: "boolean" },
            },
            fieldMapping: {
                date_start: "start_dt",
                date_stop: "stop_dt",
                date_delay: "planned_hours",
                all_day: "is_all_day",
            },
            isTimeHidden: false,
            scale: "week",
            isSmall: false,
        };
        const timed = normalizeCalendarRecord(
            {
                id: 1,
                start_dt: "2024-01-15 10:00:00",
                stop_dt: "2024-01-15 10:15:00",
                planned_hours: 0,
            },
            options,
        );
        expect(timed.duration).toBe(0.25);
        const allDay = normalizeCalendarRecord(
            {
                id: 2,
                start_dt: "2024-01-15 00:00:00",
                stop_dt: "2024-01-15 00:00:00",
                planned_hours: 0,
                is_all_day: true,
            },
            options,
        );
        expect(allDay.duration).toBe(24);
    });

    test("an empty date_delay value lasts the default hour", () => {
        const result = normalizeCalendarRecord(
            {
                id: 1,
                display_name: "X",
                start_dt: "2024-01-15 10:00:00",
                planned_hours: false,
            },
            {
                fields: { start_dt: { type: "datetime" } },
                fieldMapping: { date_start: "start_dt", date_delay: "planned_hours" },
                isTimeHidden: false,
                scale: "week",
                isSmall: false,
            },
        );

        expect(result.duration).toBe(1);
        expect(diff(result.end, result.start, "hours")).toBe(1);
    });
});

test("failed overlapping loads restore the date of the displayed records", async () => {
    const olderFilters = new Deferred();
    const newerFilters = new Deferred();
    const dates = [1, 2, 3, 4].map((day) => dateTime({ year: 2026, month: 9, day }));
    const model = Object.create(CalendarModel.prototype);
    Object.assign(model, {
        viewContext: { config: { viewId: "rollback_test" } },
        meta: {
            date: dates[0],
            scale: "day",
            scales: ["day"],
            fields: {},
            resModel: "rollback_test",
        },
        data: { records: { visibleDate: 1 } },
        keepLast: new KeepLast({ rejectSuperseded: true }),
        notify() {},
        computeRange() {
            return { start: this.meta.date };
        },
        loadFilters() {
            return this.meta.date.day === 2 ? olderFilters : newerFilters;
        },
        async fetchDateDelayFloor() {
            return undefined;
        },
        async loadRecords() {
            return { visibleDate: this.meta.date.day };
        },
        async loadDynamicFilters() {
            return {};
        },
    });
    const older = model.load({ date: dates[1] });
    const newer = model.load({ date: dates[2], transient: true });
    const rejected = expect(newer).rejects.toThrow("newer failed");
    newerFilters.reject(new Error("newer failed"));
    await rejected;
    olderFilters.resolve({ sections: {}, dynamicFiltersInfo: {} });
    await older;
    expect(model.meta.date).toBe(dates[0]);
    expect(model.data.records.visibleDate).toBe(1);
    expect("transient" in model.meta).toBe(false);
    model.loadFilters = async () => ({ sections: {}, dynamicFiltersInfo: {} });
    await model.load({ date: dates[3] });
    expect(model.data.records.visibleDate).toBe(4);
    model.loadFilters = async () => {
        throw new Error("retry failed");
    };
    await expect(model.load({ date: dates[1] })).rejects.toThrow("retry failed");
    expect(model.meta.date).toBe(dates[3]);
    expect(model.data.records.visibleDate).toBe(4);
});

function makeBareModel(overrides = {}, getters = {}) {
    const model = Object.create(
        CalendarModel.prototype,
        Object.fromEntries(
            Object.entries(getters).map(([key, value]) => [key, { value }]),
        ),
    );
    return Object.assign(model, overrides);
}

test("a date-only initial_date opens on that day west of UTC", async () => {
    patchWithCleanup(dateSettings, { timeZone: "America/Mexico_City" });
    const model = makeBareModel({
        viewContext: { config: { viewId: "initial_date_test" } },
        meta: { scale: "day", scales: ["day"], fields: {}, resModel: "event" },
        data: { records: {} },
        keepLast: new KeepLast({ rejectSuperseded: true }),
        notify() {},
        async updateData() {},
    });
    await model.load({ context: { initial_date: "2026-10-15" } });
    expect(toISODate(model.meta.date)).toBe("2026-10-15");
    expect(model.meta.date.hour).toBe(0);
});

test("a datetime initial_date still opens on its local day", async () => {
    patchWithCleanup(dateSettings, { timeZone: "America/Mexico_City" });
    const model = makeBareModel({
        viewContext: { config: { viewId: "initial_date_test" } },
        meta: { scale: "day", scales: ["day"], fields: {}, resModel: "event" },
        data: { records: {} },
        keepLast: new KeepLast({ rejectSuperseded: true }),
        notify() {},
        async updateData() {},
    });
    await model.load({ context: { initial_date: "2026-10-15 03:00:00" } });
    expect(toISODate(model.meta.date)).toBe("2026-10-14");
});

test("multi-create sets the wall-clock time on a DST day instead of adding a duration", async () => {
    patchWithCleanup(dateSettings, { timeZone: "Europe/Brussels" });
    const created = [];
    const model = makeBareModel(
        {
            meta: { resModel: "event", context: {} },
            buildRawRecord: (record) => ({ ...record }),
            orm: {
                async create(_model, records) {
                    created.push(...records);
                    return [];
                },
            },
            invalidateUnusualDays() {},
            async load() {},
        },
        { showMultiCreateTimeRange: true, filterSections: [] },
    );
    const springForward = parseISO("2024-03-31").startOfDay();
    await model.multiCreateRecords(
        {
            record: { getChanges: async () => ({}) },
            timeRange: {
                start: new Time({ hour: 12, minute: 30 }),
                end: new Time({ hour: 13 }),
            },
        },
        [springForward],
    );
    expect(created.map(({ start, end }) => [toISO(start), toISO(end)])).toEqual([
        ["2024-03-31T12:30:00.000+02:00", "2024-03-31T13:00:00.000+02:00"],
    ]);
});

test("x2many filter aggregates count each record once per related id", () => {
    patchWithCleanup(localization, {
        decimalPoint: ".",
        thousandsSep: ",",
        grouping: [3, 0],
    });
    const model = makeBareModel({
        meta: {
            aggregate: "duration:sum",
            fields: { partner_ids: { type: "many2many" } },
        },
    });
    const data = {
        records: {
            1: { rawRecord: { partner_ids: [1, 2], duration: 2 } },
            2: { rawRecord: { partner_ids: [2], duration: 3 } },
            3: { rawRecord: { partner_ids: [], duration: 5 } },
        },
    };
    const aggregates = model.computeAggregatedValues("partner_ids", data);
    expect(aggregates[1]).toBe("2");
    expect(aggregates[2]).toBe("5");
    expect(aggregates["false"]).toBe("5");
});

test("a failing filter load does not leave the unusual-days request unhandled", async () => {
    const unusualDays = new Deferred();
    const model = makeBareModel({
        meta: { showUnusualDays: true, fields: {} },
        computeRange: () => ({}),
        loadUnusualDays: () => unusualDays,
        async loadFilters() {
            throw new Error("filters failed");
        },
    });
    await expect(model.updateData({})).rejects.toThrow("filters failed");
    unusualDays.reject(new Error("unusual days failed"));
    await tick();
});
