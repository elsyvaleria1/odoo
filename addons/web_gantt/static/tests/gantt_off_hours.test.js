import { describe, expect, test } from "@odoo/hoot";
import { parseISO } from "@web/core/l10n/dates";
import {
    computeFoldableColumns,
    computeFoldedGrid,
    coveredSlots,
} from "@web_gantt/gantt_off_hours";

describe.current.tags("headless");

const dt = (iso) => parseISO(iso);

test("coveredSlots flags the slots an unavailability covers entirely", () => {
    const slot = (h1, h2) => ({
        start: dt(`2019-01-01T${h1}:00`),
        stop: dt(`2019-01-01T${h2}:00`),
    });
    const slots = [
        slot("08", "09"),
        slot("09", "10"),
        slot("10", "11"),
        slot("11", "12"),
    ];
    expect(coveredSlots(slots, [])).toEqual([0, 0, 0, 0]);
    expect(coveredSlots(slots)).toEqual([0, 0, 0, 0]);
    // 08:30 -> 10:00 covers only the 09-10 slot entirely.
    expect(coveredSlots(slots, [slot("08:30", "10:00")])).toEqual([0, 1, 0, 0]);
    // Two disjoint ones; the last slot after the last unavailability is untouched.
    expect(coveredSlots(slots, [slot("08", "09"), slot("10:00", "11:30")])).toEqual([
        1, 0, 1, 0,
    ]);
    // One that ends mid-slot still flags the slots before the cut.
    expect(coveredSlots(slots, [slot("08:00", "11:30")])).toEqual([1, 1, 1, 0]);
});

const day = (d) => ({
    start: dt(`2019-01-${String(d).padStart(2, "0")}T00:00`),
    stop: dt(`2019-01-${String(d).padStart(2, "0")}T23:59:59.999`),
});
const off = (d1, d2) => ({
    start: dt(`2019-01-${String(d1).padStart(2, "0")}T00:00`),
    stop: dt(`2019-01-${String(d2).padStart(2, "0")}T23:59:59.999`),
});

test("computeFoldableColumns: only columns every row is off for, uncrossed by a pill, in runs", () => {
    const columns = [1, 2, 3, 4, 5, 6].map(day);
    const rows = [
        { isGroup: true },
        { isGroup: false, unavailabilities: [off(1, 3), off(5, 5)] },
        { isGroup: false, unavailabilities: [off(2, 3), off(5, 6)] },
    ];
    // Day scale: a lone off column (5) is not foldable; the 2-3 run is.
    let result = computeFoldableColumns({
        columns,
        rows,
        pills: [],
        cellPart: 2,
        unit: "day",
    });
    expect(result.foldableColumns).toEqual([0, 1, 1, 0, 0, 0]);
    expect(result.foldableColumnsMapping[1]).toEqual({
        foldableGroupNum: 0,
        startIndex: 1,
        stopIndex: 2,
    });
    expect(result.foldableColumnsMapping[2]).toBe(result.foldableColumnsMapping[1]);
    // Week scale keeps the lone column.
    result = computeFoldableColumns({
        columns,
        rows,
        pills: [],
        cellPart: 2,
        unit: "week",
    });
    expect(result.foldableColumns).toEqual([0, 1, 1, 0, 1, 0]);
    expect(result.foldableColumnsMapping[4]).toEqual({
        foldableGroupNum: 1,
        startIndex: 4,
        stopIndex: 4,
    });
    // A pill over columns 2-3 (grid columns 3..7 at cellPart 2) keeps them open.
    result = computeFoldableColumns({
        columns,
        rows,
        pills: [{ grid: { column: [3, 7] } }],
        cellPart: 2,
        unit: "week",
    });
    expect(result.foldableColumns).toEqual([0, 0, 0, 0, 1, 0]);
    // A row with no unavailability folds nothing.
    result = computeFoldableColumns({
        columns,
        rows: [...rows, { isGroup: false }],
        pills: [],
        cellPart: 2,
        unit: "week",
    });
    expect(result.foldableColumns).toEqual([0, 0, 0, 0, 0, 0]);
});

test("computeFoldedGrid collapses each folded run into one grid column and maps the sub-columns", () => {
    const folded = computeFoldedGrid({
        foldableColumns: [0, 1, 1, 0],
        columnCount: 4,
        cellPart: 2,
        unit: "day",
    });
    expect(folded.foldedGridColumnSpans).toEqual([1, 2, 1]);
    expect(folded.foldedColumns).toEqual([0, 1, 1, 0]);
    expect([...folded.mappingFoldedGridToTotalGridColumnIndex]).toEqual([
        [0, 0],
        [1, 1],
        [2, 3],
    ]);
    // total sub-columns 1..8 -> folded grid sub-columns; the run's four
    // land on the folded column's two, its middle line shared.
    expect([...folded.mappingTotalGridToFoldedGridSubColumns]).toEqual([
        [1, 1],
        [2, 2],
        [3, 3],
        [4, 4],
        [5, 4],
        [6, 4],
        [7, 5],
        [8, 6],
        [9, 7],
    ]);
    // The user's own fold state ANDs with what is foldable; all-open clears.
    expect(
        computeFoldedGrid({
            foldableColumns: [0, 1, 1, 0],
            previousFoldedColumns: [0, 1, 0, 0],
            columnCount: 4,
            cellPart: 2,
            unit: "week",
        }).foldedGridColumnSpans,
    ).toEqual([1, 1, 1, 1]);
    expect(
        computeFoldedGrid({
            foldableColumns: [0, 1, 1, 0],
            previousFoldedColumns: [0, 0, 0, 0],
            columnCount: 4,
            cellPart: 2,
            unit: "day",
        }),
    ).toBe(null);
});
