import { describe, expect, test } from "@odoo/hoot";
import { patchWithCleanup } from "@web/../tests/web_test_helpers";
import { parseISO, toISODate } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { visibleColumns } from "@web_gantt/gantt_columns";
import { GridGeometry } from "@web_gantt/gantt_grid_geometry";

describe.current.tags("headless");

const dt = (iso) => parseISO(iso);
const WEEK_HALF = {
    interval: "day",
    cellPart: 2,
    cellTime: 12,
    time: "hour",
    unit: "week",
};

function window(params) {
    const globalStart = dt("2019-01-07");
    return visibleColumns({
        firstIndex: 0,
        lastIndex: 13,
        columnCount: 14,
        scale: WEEK_HALF,
        globalStart,
        globalStop: dt("2019-01-21"),
        displayUnavailability: false,
        indexInTotalGrid: (i) => i,
        geometry: new GridGeometry(globalStart, WEEK_HALF),
        now: dt("2019-01-09T10:00"),
        ...params,
    });
}

test("an unfolded window: one column per day, two sub-columns each, a group per week", () => {
    patchWithCleanup(localization, { weekStart: 1 });
    const { columns, subColumns, columnsGroups, coarseGridCols } = window({});
    expect(columns).toHaveLength(14);
    expect(columns[0].grid.column).toEqual([1, 3]);
    expect(columns[13].grid.column).toEqual([27, 29]);
    expect(columns.map((c) => Boolean(c.isToday))).toEqual([
        false,
        false,
        true,
        ...Array(11).fill(false),
    ]);
    expect(subColumns).toHaveLength(28);
    expect(subColumns[5]).toMatchObject({ columnIndex: 2, isToday: true });
    expect(columnsGroups.map((g) => g.grid.column)).toEqual([
        [1, 15],
        [15, 29],
    ]);
    expect(columnsGroups.map((g) => g.isFolded)).toEqual([false, false]);
    expect(Object.keys(coarseGridCols)).toHaveLength(29);
});

test("a partial window keeps each group header on its whole week", () => {
    patchWithCleanup(localization, { weekStart: 1 });
    const { columns, columnsGroups } = window({ firstIndex: 5, lastIndex: 9 });
    expect(columns.map((c) => c.index)).toEqual([5, 6, 7, 8, 9]);
    expect(columnsGroups.map((g) => g.grid.column)).toEqual([
        [1, 15],
        [15, 29],
    ]);
});

test("a folded run collapses into one column that spans it and keeps no sub-columns", () => {
    patchWithCleanup(localization, { weekStart: 1 });
    const foldedColumns = [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0];
    const spans = [1, 1, 1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1];
    const toTotal = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13];
    const { columns, subColumns } = window({
        lastIndex: 12,
        foldedGridColumnSpans: spans,
        foldedColumns,
        indexInTotalGrid: (i) => toTotal[i],
    });
    expect(columns).toHaveLength(13);
    const folded = columns[5];
    expect(folded.isFolded).toBe(true);
    expect(folded.grid.column).toEqual([11, 15]);
    expect(toISODate(folded.stop)).toBe("2019-01-13");
    expect(subColumns).toHaveLength(24);
    expect(subColumns.some((s) => s.columnIndex === 5 || s.columnIndex === 6)).toBe(
        false,
    );
});

test("with unavailabilities shown, a column knows whether it ends a foldable run", () => {
    patchWithCleanup(localization, { weekStart: 1 });
    const { columns } = window({
        displayUnavailability: true,
        foldableColumnsMapping: { 5: { stopIndex: 6 }, 6: { stopIndex: 6 } },
    });
    expect(columns.map((c) => c.isFoldable)).toEqual([
        0,
        0,
        0,
        0,
        0,
        1,
        "stop",
        0,
        0,
        0,
        0,
        0,
        0,
        0,
    ]);
});
