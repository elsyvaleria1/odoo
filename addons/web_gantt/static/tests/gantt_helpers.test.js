import { describe, expect, test } from "@odoo/hoot";
import { mockTimeZone } from "@odoo/hoot-mock";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import {
    DATETIME_SHORT,
    endOf,
    parseISO,
    TIME_SIMPLE,
    toISO,
    toISODate,
    toLocaleString,
} from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import {
    dateAddFixedOffset,
    diffColumn,
    getBadges,
    getCellColor,
    getUnionOfIntersections,
    localEndOf,
    localStartOf,
} from "@web_gantt/gantt_helpers";

describe.current.tags("headless");

const dt = (iso) => parseISO(iso);

test("dateAddFixedOffset keeps the wall-clock hour across a DST change", () => {
    mockTimeZone("Europe/Brussels");
    // 2019-03-31 02:00 -> 03:00 in Brussels
    const before = dt("2019-03-30T08:00:00");
    expect(toISO(dateAddFixedOffset(before, { hours: 24 }))).toBe(
        toISO(dt("2019-03-31T08:00:00")),
    );
    expect(toISO(dateAddFixedOffset(before, { days: 1 }))).toBe(
        toISO(dt("2019-03-31T08:00:00")),
    );
    // 2019-10-27 03:00 -> 02:00
    const fall = dt("2019-10-26T08:00:00");
    expect(toISO(dateAddFixedOffset(fall, { hours: 24 }))).toBe(
        toISO(dt("2019-10-27T08:00:00")),
    );
    // A plain add() drifts by the offset change; the helper is what hides it.
    expect(fall.add({ hours: 24 }).hour).toBe(7);
});

test("dateAddFixedOffset leaves non-time units alone", () => {
    mockTimeZone("Europe/Brussels");
    const d = dt("2019-03-30T08:00:00");
    expect(toISO(dateAddFixedOffset(d, { month: 1 }))).toBe(
        toISO(d.add({ months: 1 })),
    );
});

test("diffColumn counts whole units between two boundaries", () => {
    expect(diffColumn(dt("2019-01-01"), dt("2019-01-08"), "day")).toBe(7);
    expect(diffColumn(dt("2019-01-01"), dt("2019-03-01"), "month")).toBe(2);
    expect(diffColumn(dt("2019-01-01T00:00"), dt("2019-01-01T05:00"), "hour")).toBe(5);
});

test("localStartOf and localEndOf follow the locale week start", () => {
    const wednesday = dt("2026-09-09T15:00:00");
    patchWithCleanup(localization, { weekStart: 1 });
    expect(toISODate(localStartOf(wednesday, "week"))).toBe("2026-09-07");
    expect(toISODate(localEndOf(wednesday, "week"))).toBe("2026-09-13");
    patchWithCleanup(localization, { weekStart: 7 });
    expect(toISODate(localStartOf(wednesday, "week"))).toBe("2026-09-06");
    expect(toISODate(localEndOf(wednesday, "week"))).toBe("2026-09-12");
    // Any other unit is the plain calendar boundary.
    expect(toISODate(localStartOf(wednesday, "month"))).toBe("2026-09-01");
    expect(toISO(localEndOf(wednesday, "day"))).toBe(toISO(endOf(wednesday, "day")));
});

test("getUnionOfIntersections clips the outer intervals and keeps the inner ones", () => {
    const interval = [dt("2019-01-05"), dt("2019-01-20")];
    const intervals = [
        [dt("2019-01-01"), dt("2019-01-03")], // before
        [dt("2019-01-02"), dt("2019-01-07")], // overlaps the start
        [dt("2019-01-10"), dt("2019-01-12")], // inside
        [dt("2019-01-18"), dt("2019-01-25")], // overlaps the end
        [dt("2019-01-26"), dt("2019-01-28")], // after
    ];
    const union = getUnionOfIntersections(interval, intervals);
    expect(union.map(([a, b]) => [toISODate(a), toISODate(b)])).toEqual([
        ["2019-01-05", "2019-01-07"],
        ["2019-01-10", "2019-01-12"],
        ["2019-01-18", "2019-01-20"],
    ]);
    expect(getUnionOfIntersections(interval, [intervals[0], intervals[4]])).toEqual([]);
    // A single intersecting interval is clipped on both sides.
    expect(
        getUnionOfIntersections(interval, [[dt("2019-01-01"), dt("2019-01-31")]]).map(
            ([a, b]) => [toISODate(a), toISODate(b)],
        ),
    ).toEqual([["2019-01-05", "2019-01-20"]]);
});

test("getCellColor: nothing off is null, everything off is flat, otherwise a gradient", () => {
    expect(getCellColor(2, [0, 0], false)).toBe(null);
    expect(getCellColor(2, [1, 1], false)).toBe(
        "background-color:var(--Gantt__DayOff-background-color)",
    );
    expect(getCellColor(2, [1, 0], true)).toBe(
        "background:linear-gradient(90deg,var(--Gantt__DayOff-background-color)49%,var(--Gantt__DayOffToday-background-color)50%)",
    );
    expect(getCellColor(4, [1, 1, 0, 0], false)).toMatch(
        /^background:linear-gradient\(90deg,/,
    );
    // Four sub-slots draw six stops, the two inner ones twice.
    expect(
        getCellColor(4, [1, 1, 0, 0], false).match(/DayOff-background/g),
    ).toHaveLength(3);
    expect(getCellColor(4, [1, 1, 0, 0], false).match(/Day-background/g)).toHaveLength(
        3,
    );
});

test("getBadges adds the date once a drag on the day scale crosses midnight", () => {
    const el = {
        getBoundingClientRect: () => ({
            x: 100,
            y: 50,
            width: 80,
            height: 20,
            top: 50,
        }),
        closest: () => null,
    };
    const scale = { cellPart: 4, time: "minute", unitDescription: "minutes" };
    const same = getBadges(
        el,
        [dt("2019-01-01T22:00:00"), 0],
        [dt("2019-01-01T23:30:00"), 0],
        { rtl: false, scale },
    );
    expect(same.startBadge.text).toBe(
        toLocaleString(dt("2019-01-01T22:00:00"), TIME_SIMPLE),
    );
    const across = getBadges(
        el,
        [dt("2019-01-01T23:30:00"), 0],
        [dt("2019-01-02T00:30:00"), 30],
        { rtl: false, scale },
    );
    expect(across.startBadge.text).toBe(
        toLocaleString(dt("2019-01-01T23:30:00"), DATETIME_SHORT),
    );
    expect(across.stopBadge.text).toBe(
        `${toLocaleString(dt("2019-01-02T00:30:00"), DATETIME_SHORT)} (+30 minutes)`,
    );
    expect(across.stopBadge.class).toBe("text-success");
});
