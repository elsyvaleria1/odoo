import { describe, expect, test } from "@odoo/hoot";
import {
    assignPillLevels,
    colsTemplate,
    columnWidths,
    firstSelectedRun,
    focusFactorAt,
    FOLDED_COLUMN_WIDTH,
    parseCellKey,
    rowsTemplate,
    subColumnsDistance,
} from "@web_gantt/gantt_layout";
import { foldedRuns } from "@web_gantt/gantt_off_hours";

describe.current.tags("headless");

const pill = (a, b) => ({ grid: { column: [a, b] } });

test("assignPillLevels stacks overlapping pills and reuses a level once it is free", () => {
    expect(assignPillLevels([])).toBe(0);
    const pills = [pill(1, 5), pill(3, 7), pill(5, 9), pill(7, 8), pill(9, 12)];
    expect(assignPillLevels(pills)).toBe(2);
    expect(pills.map((p) => p.level)).toEqual([0, 1, 0, 1, 0]);
    expect(assignPillLevels([pill(1, 5), pill(5, 9)])).toBe(1);
    const three = [pill(1, 4), pill(2, 4), pill(2, 3)];
    expect(assignPillLevels(three)).toBe(3);
    expect(three.map((p) => p.level)).toEqual([0, 1, 2]);
});

test("assignPillLevels overwrites a level a stale copy may carry", () => {
    const pills = [pill(1, 3), pill(4, 6)];
    pills[1].level = 5;
    assignPillLevels(pills);
    expect(pills[1].level).toBe(0);
});

test("parseCellKey reads the four numbers of a cell key", () => {
    expect(parseCellKey("3_5_7_8")).toEqual({
        startRow: 3,
        endRow: 5,
        startCol: 7,
        endCol: 8,
    });
});

test("firstSelectedRun extends the first block over its right-hand neighbours only", () => {
    const b = (row, c1, c2) => ({
        startRow: row,
        endRow: row + 2,
        startCol: c1,
        endCol: c2,
    });
    expect(firstSelectedRun([b(3, 5, 6), b(1, 4, 5), b(1, 2, 3), b(1, 3, 4)])).toEqual(
        b(1, 2, 5),
    );
    expect(firstSelectedRun([b(1, 2, 3), b(1, 4, 5), b(1, 5, 6)])).toEqual(b(1, 2, 3));
    expect(firstSelectedRun([b(1, 2, 3), b(3, 3, 4)])).toEqual(b(1, 2, 3));
    const blocks = [b(1, 2, 3), b(1, 3, 4)];
    firstSelectedRun(blocks);
    expect(blocks[0].endCol).toBe(3);
});

test("rowsTemplate names each coarse row line and sums the fine rows it spans", () => {
    expect(rowsTemplate([1, 3, 4], [25, 10, 25])).toBe("[r1]35px[r3]25px[r4]");
    expect(rowsTemplate(["1", "2"], [40])).toBe("[r1]40px[r2]");
});

test("foldedRuns keeps open columns apart and merges folded stretches", () => {
    expect(foldedRuns([])).toEqual([]);
    expect(foldedRuns([0, 0])).toEqual([
        { folded: false, length: 1 },
        { folded: false, length: 1 },
    ]);
    expect(foldedRuns([0, 1, 1, 0, 1])).toEqual([
        { folded: false, length: 1 },
        { folded: true, length: 2 },
        { folded: false, length: 1 },
        { folded: true, length: 1 },
    ]);
});

test("columnWidths shares the content width and reports an overflow", () => {
    const base = {
        contentWidth: 1000,
        rowHeaderWidth: 200,
        cellPart: 2,
        minimalColumnWidth: 40,
        columnCount: 8,
        foldedGridColumnCount: 8,
    };
    let w = columnWidths(base);
    expect(w).toMatchObject({ cellPartWidth: 50, columnWidth: 100, totalWidth: null });
    expect(w.columnWidths).toEqual(new Array(8).fill(100));
    w = columnWidths({ ...base, columnCount: 1, foldedGridColumnCount: 1 });
    expect(w).toMatchObject({
        columnWidth: 800,
        columnWidths: [800],
        totalWidth: null,
    });
    w = columnWidths({ ...base, columnCount: 40, foldedGridColumnCount: 40 });
    expect(w.columnWidth).toBe(40);
    expect(w.totalWidth).toBe(40 * 40 + 200);
    const foldedColumns = [0, 0, 1, 1, 0, 0, 0, 0];
    w = columnWidths({ ...base, foldedGridColumnCount: 7, foldedColumns });
    expect(w.columnWidths).toEqual([
        w.columnWidth,
        w.columnWidth,
        FOLDED_COLUMN_WIDTH,
        ...new Array(4).fill(w.columnWidth),
    ]);
    expect(w.columnWidth).toBe(Math.floor(Math.floor((800 - 36) / 6) / 2) * 2);
});

test("colsTemplate names each coarse line and sizes the track between", () => {
    const distance = (x, y) => ({ distance: (y - x) * 10, flexible: y - x < 3 });
    expect(colsTemplate([1, 3, 6], distance)).toBe(
        "[c1]minmax(20px,1fr)[c3]minmax(30px,0fr)[c6]",
    );
});

test("focusFactorAt reads a position off the container, or off the folded widths", () => {
    const open = {
        cellContainerWidth: 800,
        columnWidths: new Array(8).fill(100),
        columnCount: 8,
        indexInTotalGrid: (i) => i,
    };
    expect(focusFactorAt(400, open)).toBe(0.5);
    expect(focusFactorAt(0, open)).toBe(0);
    const toTotal = [0, 1, 2, 4, 5, 6, 7];
    const folded = {
        cellContainerWidth: 636,
        columnWidths: [100, 100, FOLDED_COLUMN_WIDTH, 100, 100, 100, 100],
        columnCount: 8,
        indexInTotalGrid: (i) => toTotal[i],
    };
    expect(focusFactorAt(150, folded)).toBe(2 / 8);
    expect(focusFactorAt(220, folded)).toBe(3 / 8);
    expect(focusFactorAt(700, folded)).toBe(700 / 636);
});

test("subColumnsDistance counts open sub-columns at their width and folded ones at a share of the fixed width", () => {
    const unfolded = subColumnsDistance(1, 5, {
        cellPart: 2,
        cellPartWidth: 50,
        colNumberInFoldedGrid: (c) => c,
        indexInTotalGrid: (i) => i,
    });
    expect(unfolded).toEqual({ distance: 200, flexible: true });
    const params = {
        cellPart: 2,
        cellPartWidth: 50,
        foldedGridColumnSpans: [1, 1, 1, 1],
        foldedColumns: [0, 1, 0, 0],
        colNumberInFoldedGrid: (c) => c,
        indexInTotalGrid: (i) => i,
    };
    expect(subColumnsDistance(1, 3, params)).toEqual({ distance: 100, flexible: true });
    expect(subColumnsDistance(3, 5, params)).toEqual({ distance: 36, flexible: false });
    expect(subColumnsDistance(1, 9, params)).toEqual({
        distance: 336,
        flexible: false,
    });
});
