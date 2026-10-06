/** @odoo-module native */
import { compareDates } from "@web/core/l10n/dates";
import { zipWith } from "@web/core/utils/collections/arrays";

/**
 * @typedef {Temporal.ZonedDateTime} DateTime
 * @typedef {{ start: DateTime, stop: DateTime }} Slot
 */

/**
 * Which slots an ordered, pairwise-disjoint list of unavailabilities covers
 * entirely. Both the cell colours and the foldable columns are this scan.
 *
 * @param {Slot[]} slots -- ordered
 * @param {Slot[]} [unavailabilities] -- ordered, disjoint
 * @returns {(0 | 1)[]} one flag per slot
 */
export function coveredSlots(slots, unavailabilities = []) {
    const covered = new Array(slots.length).fill(0);
    let index = 0;
    for (let s = 0; s < slots.length && index < unavailabilities.length; s++) {
        const { start, stop } = slots[s];
        while (
            index < unavailabilities.length &&
            compareDates(stop, unavailabilities[index].stop) > 0
        ) {
            index++;
        }
        if (
            index < unavailabilities.length &&
            compareDates(unavailabilities[index].start, start) <= 0
        ) {
            covered[s] = 1;
        }
    }
    return covered;
}

/**
 * @param {(0 | 1)[]} foldedColumns -- one flag per total-grid column
 * @returns {{ folded: boolean, length: number }[]}
 */
export function foldedRuns(foldedColumns) {
    const runs = [];
    for (const flag of foldedColumns) {
        const last = runs.at(-1);
        if (flag && last?.folded) {
            last.length++;
        } else {
            runs.push({ folded: Boolean(flag), length: 1 });
        }
    }
    return runs;
}

/**
 * @param {Object} params
 * @param {Slot[]} params.columns
 * @param {{ isGroup: boolean, unavailabilities?: Slot[] }[]} params.rows
 * @param {{ grid: { column: [number, number] } }[]} params.pills
 * @param {number} params.cellPart
 * @param {string} params.unit
 * @returns {{ foldableColumns: (0 | 1)[], foldableColumnsMapping: Record<number, { foldableGroupNum: number, startIndex: number, stopIndex?: number }> }}
 */
export function computeFoldableColumns({ columns, rows, pills, cellPart, unit }) {
    const foldableColumns = Array(columns.length).fill(1);
    let allNull = true;
    for (const row of rows) {
        if (row.isGroup) {
            continue;
        }
        allNull = true;
        const covered = coveredSlots(columns, row.unavailabilities);
        for (let columnIndex = 0; columnIndex < columns.length; columnIndex++) {
            foldableColumns[columnIndex] &= covered[columnIndex] ?? 0;
            if (foldableColumns[columnIndex]) {
                allNull = false;
            }
        }
        if (allNull) {
            break;
        }
    }
    if (allNull) {
        foldableColumns.fill(0);
    } else {
        for (const pill of pills) {
            foldableColumns.fill(
                0,
                Math.floor((pill.grid.column[0] - 1) / cellPart),
                Math.ceil((pill.grid.column[1] - 1) / cellPart),
            );
        }
    }

    const foldableColumnsMapping = {};
    let foldableGroupNum = 0;
    let foldableSubSet;
    for (let i = 0; i < foldableColumns.length; i++) {
        if (foldableColumns[i]) {
            const next = foldableColumns[i + 1];
            const previous = foldableColumns[i - 1];
            if (!previous) {
                foldableSubSet = { foldableGroupNum };
                foldableGroupNum++;
                foldableSubSet.startIndex = i;
            }
            if (next === 1) {
                foldableColumnsMapping[i] = foldableSubSet;
                continue;
            }
            if (!previous && unit !== "week") {
                foldableColumns[i] = 0;
                continue;
            }
            foldableSubSet.stopIndex = i;
            foldableColumnsMapping[i] = foldableSubSet;
        }
    }
    return { foldableColumns, foldableColumnsMapping };
}

/**
 * The folded grid: each run of folded columns collapses to one grid column,
 * with the sub-columns of the total grid mapped onto it.
 *
 * @param {Object} params
 * @param {(0 | 1)[]} params.foldableColumns
 * @param {(0 | 1)[]} [params.previousFoldedColumns] -- the user's fold state, if any
 * @param {number} params.columnCount
 * @param {number} params.cellPart
 * @param {string} params.unit
 * @returns {null | { foldedGridColumnSpans: number[], mappingTotalGridToFoldedGridSubColumns: Map<number, number>, foldedColumns: (0 | 1)[], mappingFoldedGridToTotalGridColumnIndex: Map<number, number> }}
 *   null when nothing is folded any more
 */
export function computeFoldedGrid({
    foldableColumns,
    previousFoldedColumns,
    columnCount,
    cellPart,
    unit,
}) {
    if (previousFoldedColumns && !previousFoldedColumns.includes(1)) {
        return null;
    }
    let folded = foldableColumns;
    if (previousFoldedColumns?.length === columnCount) {
        folded = zipWith(foldableColumns, previousFoldedColumns, (a, b) => a & b);
    }

    const foldedGridColumnSpans = foldedRuns(folded).map((run) => run.length);

    const mappingTotalGridToFoldedGridSubColumns = new Map();
    const foldedColumns = [];
    const halfCut = Math.floor(cellPart / 2);
    let count = 0;
    for (let index = 0; index < foldedGridColumnSpans.length; index++) {
        const val = foldedGridColumnSpans[index];
        if (val > 1) {
            for (let j = 0; j < val; j++) {
                for (let i = 1; i <= cellPart; i++) {
                    const targetIndex =
                        j === 0
                            ? index * cellPart + (i <= halfCut ? i : halfCut + 1)
                            : j === val - 1
                              ? index * cellPart + (i <= halfCut ? halfCut + 1 : i)
                              : index * cellPart + halfCut + 1;
                    mappingTotalGridToFoldedGridSubColumns.set(
                        count * cellPart + i,
                        targetIndex,
                    );
                }
                count++;
                foldedColumns.push(1);
            }
        } else {
            for (let i = 1; i <= cellPart; i++) {
                mappingTotalGridToFoldedGridSubColumns.set(
                    count * cellPart + i,
                    index * cellPart + i,
                );
            }
            foldedColumns.push(folded[count] && unit === "week" ? 1 : 0);
            count++;
        }
    }
    mappingTotalGridToFoldedGridSubColumns.set(
        columnCount * cellPart + 1,
        foldedGridColumnSpans.length * cellPart + 1,
    );
    let colIndex = 0;
    const mappingFoldedGridToTotalGridColumnIndex = new Map(
        foldedGridColumnSpans.map((val, gridIndex) => {
            const res = [gridIndex, colIndex];
            colIndex += val;
            return res;
        }),
    );
    return {
        foldedGridColumnSpans,
        mappingTotalGridToFoldedGridSubColumns,
        foldedColumns,
        mappingFoldedGridToTotalGridColumnIndex,
    };
}
