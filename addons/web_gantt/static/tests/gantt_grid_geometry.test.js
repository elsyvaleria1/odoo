import { describe, expect, test } from "@odoo/hoot";
import { mockTimeZone } from "@odoo/hoot-mock";
import { parseISO, toISO } from "@web/core/l10n/dates";
import { GridGeometry } from "@web_gantt/gantt_grid_geometry";

describe.current.tags("headless");

const dt = (iso) => parseISO(iso);
const DAY_HALF = { interval: "day", cellPart: 2, cellTime: 12, time: "hour" };
const HOUR_QUARTER = { interval: "hour", cellPart: 4, cellTime: 15, time: "minute" };

test("columns and sub-columns of a half-day grid", () => {
    const g = new GridGeometry(dt("2019-01-01T00:00"), DAY_HALF);
    expect(g.columnIndexFromDate(dt("2019-01-01T00:00"))).toBe(0);
    expect(g.columnIndexFromDate(dt("2019-01-04T00:00"))).toBe(3);
    // Grid line 1 is column 0's first half, line 3 column 1's first half.
    expect(g.columnIndexFromColNumber(1)).toBe(0);
    expect(g.columnIndexFromColNumber(2)).toBe(0);
    expect(g.columnIndexFromColNumber(3)).toBe(1);
    expect(toISO(g.columnFromColNumber(3).start)).toBe(toISO(dt("2019-01-02T00:00")));
    const sub = g.subColumnFromColNumber(4);
    expect(toISO(sub.start)).toBe(toISO(dt("2019-01-02T12:00")));
    expect(toISO(sub.stop)).toBe(toISO(dt("2019-01-02T23:59:59")));
    // A record from the 2nd at noon to the 4th at 06:00 spans lines 4 -> 7.
    expect(
        g.gridColumnFromDates(dt("2019-01-02T12:00"), dt("2019-01-04T06:00")),
    ).toEqual([4, 8]);
    // A stop exactly on a boundary does not reach into the next sub-column.
    expect(
        g.gridColumnFromDates(dt("2019-01-02T00:00"), dt("2019-01-02T12:00")),
    ).toEqual([3, 4]);
});

test("sub-column edges: a start rounds down, a stop rounds up", () => {
    const g = new GridGeometry(dt("2019-01-01T08:00"), HOUR_QUARTER);
    expect(g.subColumnFromDate(dt("2019-01-01T08:20"))).toEqual({
        column: dt("2019-01-01T08:00"),
        delta: 1,
    });
    expect(g.subColumnFromDate(dt("2019-01-01T08:20"), false)).toEqual({
        column: dt("2019-01-01T08:00"),
        delta: 2,
    });
    expect(g.subColumnFromDate(dt("2019-01-01T08:15"), false).delta).toBe(1);
    expect(g.subColumnFromDate(dt("2019-01-01T08:15")).delta).toBe(1);
});

test("a DST day with no midnight still yields whole columns", () => {
    mockTimeZone("Europe/Brussels");
    // Range starting before the spring-forward night; 2019-03-31 02:00 -> 03:00.
    const g = new GridGeometry(dt("2019-03-29T00:00"), DAY_HALF);
    const [first, last] = g.gridColumnFromDates(
        dt("2019-03-31T10:00"),
        dt("2019-04-01T10:00"),
    );
    expect(Number.isInteger(first)).toBe(true);
    expect(Number.isInteger(last)).toBe(true);
    // 29th, 30th, 31st -> column 2, morning half; the 1st at 10:00 ends in
    // column 3's first half, so the pill reaches line 8.
    expect([first, last]).toEqual([5, 8]);
});

test("boundaries are memoised per column", () => {
    const g = new GridGeometry(dt("2019-01-01T00:00"), DAY_HALF);
    const a = g.subCellStarts(dt("2019-01-03T00:00"));
    const b = g.subCellStarts(dt("2019-01-03T00:00"));
    expect(a).toBe(b);
    expect(a).toHaveLength(2);
    expect(g.columnFromColNumber(5)).toBe(g.columnFromColNumber(5));
    expect(g.columnFromColNumber(5)).toEqual(g.columnFromColNumber(6));
});
