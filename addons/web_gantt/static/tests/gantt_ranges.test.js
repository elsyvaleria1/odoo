import { describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { parseISO, toISODate } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import {
    customRangeAround,
    firstColumnAfter,
    normalizeRange,
} from "@web_gantt/gantt_ranges";

describe.current.tags("headless");

const dt = (iso) => parseISO(iso);
const iso = (d) => toISODate(d);

test("firstColumnAfter is the date itself on a boundary, else the next one", () => {
    expect(iso(firstColumnAfter(dt("2019-03-01"), "month"))).toBe("2019-03-01");
    expect(iso(firstColumnAfter(dt("2019-03-02"), "month"))).toBe("2019-04-01");
    patchWithCleanup(localization, { weekStart: 1 });
    expect(iso(firstColumnAfter(dt("2026-09-09"), "week"))).toBe("2026-09-14");
});

test("normalizeRange orders the bounds and snaps them to the column grid", () => {
    const r = normalizeRange({
        startDate: dt("2019-03-20"),
        stopDate: dt("2019-03-05"),
        interval: "month",
    });
    expect(iso(r.startDate)).toBe("2019-03-05");
    expect(iso(r.stopDate)).toBe("2019-03-20");
    expect(iso(r.globalStart)).toBe("2019-03-01");
    // The stop day is inclusive: the grid ends at the boundary after it.
    expect(iso(r.globalStop)).toBe("2019-04-01");
    const day = normalizeRange({
        startDate: dt("2019-03-05"),
        stopDate: dt("2019-03-05"),
        interval: "day",
    });
    expect(iso(day.globalStart)).toBe("2019-03-05");
    expect(iso(day.globalStop)).toBe("2019-03-06");
});

test("normalizeRange clamps a range past ten years on the side that did not move", () => {
    const forward = normalizeRange({
        startDate: dt("2019-01-01"),
        stopDate: dt("2040-01-01"),
        interval: "year",
    });
    expect(iso(forward.startDate)).toBe("2019-01-01");
    expect(iso(forward.stopDate)).toBe("2028-12-31");
    // Given backwards, the stop is what the user set, so the start gives way.
    const backward = normalizeRange({
        startDate: dt("2040-01-01"),
        stopDate: dt("2019-01-01"),
        interval: "year",
    });
    expect(iso(backward.startDate)).toBe("2030-01-02");
    expect(iso(backward.stopDate)).toBe("2040-01-01");
});

test("normalizeRange keeps the focus date inside the range", () => {
    const base = {
        startDate: dt("2019-03-01"),
        stopDate: dt("2019-03-31"),
        interval: "day",
    };
    expect(normalizeRange(base).focusDate).toBe(undefined);
    expect(
        iso(normalizeRange({ ...base, focusDate: dt("2019-03-15") }).focusDate),
    ).toBe("2019-03-15");
    expect(
        iso(normalizeRange({ ...base, focusDate: dt("2019-01-15") }).focusDate),
    ).toBe("2019-03-01");
    expect(
        iso(normalizeRange({ ...base, focusDate: dt("2019-05-15") }).focusDate),
    ).toBe("2019-03-31");
});

test("customRangeAround: three months from a start, up to a stop, or around the focus", () => {
    const today = dt("2019-06-15");
    const focus = dt("2019-03-20");
    const around = customRangeAround({ focusDate: focus, today });
    expect([
        iso(around.startDate),
        iso(around.stopDate),
        iso(around.focusDate),
    ]).toEqual(["2019-03-01", "2019-05-31", "2019-03-20"]);
    const from = customRangeAround({
        startDate: dt("2019-03-20"),
        focusDate: focus,
        today,
    });
    expect([iso(from.startDate), iso(from.stopDate), iso(from.focusDate)]).toEqual([
        "2019-03-20",
        "2019-05-31",
        "2019-03-20",
    ]);
    const upTo = customRangeAround({
        stopDate: dt("2019-03-20"),
        focusDate: focus,
        today,
    });
    expect([iso(upTo.startDate), iso(upTo.stopDate), iso(upTo.focusDate)]).toEqual([
        "2019-01-01",
        "2019-03-20",
        "2019-03-20",
    ]);
    // Both given: the pair as is, today as the focus unless it lies outside.
    const both = {
        startDate: dt("2019-03-01"),
        stopDate: dt("2019-03-31"),
        focusDate: focus,
    };
    expect(iso(customRangeAround({ ...both, today: dt("2019-03-10") }).focusDate)).toBe(
        "2019-03-10",
    );
    expect(iso(customRangeAround({ ...both, today }).focusDate)).toBe("2019-03-31");
    expect(iso(customRangeAround({ ...both, today: dt("2018-01-01") }).focusDate)).toBe(
        "2019-03-01",
    );
});
