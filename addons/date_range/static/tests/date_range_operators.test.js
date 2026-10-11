import "@date_range/js/date_range_provider";

import { setDateRanges } from "@date_range/js/date_range_provider";
import { describe, expect, test } from "@odoo/hoot";
import { mockTimeZone } from "@odoo/hoot-mock";
import { makeMockEnv } from "@web/../tests/web_test_helpers";
import {
    getInRangeProviderOptions,
    matchInRangeProviderOption,
    resolveInRangeProviderOption,
} from "@web/core/tree";

describe.current.tags("headless");

const RANGES = [
    {
        id: 7,
        name: "Q1 2030",
        date_start: "2030-01-01",
        date_end: "2030-03-31",
        type_id: [3, "Quarter"],
    },
    {
        id: 8,
        name: "H1 2030",
        date_start: "2030-01-01",
        date_end: "2030-06-30",
        type_id: [4, "Half"],
    },
];

function withRanges(ranges = RANGES) {
    setDateRanges(ranges);
}

test("periods are offered, grouped by their type", async () => {
    await makeMockEnv();
    withRanges();
    const options = getInRangeProviderOptions("date");
    expect(options.map((o) => o.label)).toEqual(["Q1 2030", "H1 2030"]);
    expect(options.map((o) => o.group)).toEqual([
        "Periods / Quarter",
        "Periods / Half",
    ]);
});

test("a non-date field is offered no periods", async () => {
    await makeMockEnv();
    withRanges();
    expect(getInRangeProviderOptions("char")).toEqual([]);
    expect(getInRangeProviderOptions("integer")).toEqual([]);
});

test("picking a period on a date field yields its plain dates", async () => {
    await makeMockEnv();
    withRanges();
    expect(resolveInRangeProviderOption("date_range:7", "date")).toEqual([
        "2030-01-01",
        "2030-03-31",
    ]);
});

test("picking a period on a datetime field covers both of its end days", async () => {
    await makeMockEnv();
    mockTimeZone(0);
    withRanges();
    expect(resolveInRangeProviderOption("date_range:7", "datetime")).toEqual([
        "2030-01-01 00:00:00",
        "2030-03-31 23:59:59",
    ]);
});

test("the period's end days follow the user's timezone", async () => {
    await makeMockEnv();
    mockTimeZone(2);
    withRanges();
    const [start, end] = resolveInRangeProviderOption("date_range:7", "datetime");
    expect(start).toBe("2029-12-31 22:00:00");
    expect(end).toBe("2030-03-31 21:59:59");
    expect(matchInRangeProviderOption("datetime", start, end)).toBe("date_range:7");
});

test("a stored range whose bounds match a period is offered back as one", async () => {
    await makeMockEnv();
    withRanges();
    expect(matchInRangeProviderOption("date", "2030-01-01", "2030-03-31")).toBe(
        "date_range:7",
    );
    expect(matchInRangeProviderOption("date", "2030-01-01", "2030-06-30")).toBe(
        "date_range:8",
    );
});

test("bounds naming no period stay a custom range", async () => {
    await makeMockEnv();
    withRanges();
    expect(matchInRangeProviderOption("date", "2030-01-02", "2030-03-31")).toBe(null);
    expect(matchInRangeProviderOption("date", false, false)).toBe(null);
    expect(
        matchInRangeProviderOption("date", { _expr: "context_today()" }, "2030-03-31"),
    ).toBe(null);
});

test("no loaded ranges degrades to the built-in value types", async () => {
    await makeMockEnv();
    withRanges([]);
    expect(getInRangeProviderOptions("date")).toEqual([]);
    expect(matchInRangeProviderOption("date", "2030-01-01", "2030-03-31")).toBe(null);
    expect(resolveInRangeProviderOption("date_range:7", "date")).toBe(null);
});

test("an unknown option id resolves to nothing", async () => {
    await makeMockEnv();
    withRanges();
    expect(resolveInRangeProviderOption("date_range:999", "date")).toBe(null);
    expect(resolveInRangeProviderOption("something_else:7", "date")).toBe(null);
});
