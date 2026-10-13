/** @odoo-module native */
import { foldedRuns } from "./gantt_off_hours.js";

export const FOLDED_COLUMN_WIDTH = 36;

/**
 * @typedef {{ grid: { column: [number, number] }, level?: number }} Placed
 * @typedef {{ startRow: number, endRow: number, startCol: number, endCol: number }} Block
 */

/**
 * @param {Placed[]} pills
 * @returns {number}
 */
export function assignPillLevels(pills) {
    if (!pills.length) {
        return 0;
    }
    const [firstPill] = pills;
    firstPill.level = 0;
    const levels = [{ maxCol: firstPill.grid.column[1] - 1 }];
    for (const pill of pills.slice(1)) {
        const [firstCol, lastCol] = pill.grid.column;
        pill.level = undefined;
        for (let l = 0; l < levels.length; l++) {
            if (firstCol > levels[l].maxCol) {
                pill.level = l;
                levels[l].maxCol = lastCol - 1;
                break;
            }
        }
        if (pill.level === undefined) {
            pill.level = levels.length;
            levels.push({ maxCol: lastCol - 1 });
        }
    }
    return levels.length;
}

/**
 * @param {string} cellKey
 * @returns {Block}
 */
export function parseCellKey(cellKey) {
    const [startRow, endRow, startCol, endCol] = cellKey.split("_").map(Number);
    return { startRow, endRow, startCol, endCol };
}

/**
 * @param {Block[]} blocks
 * @returns {Block}
 */
export function firstSelectedRun(blocks) {
    const sorted = [...blocks].sort(
        (b1, b2) => b1.startRow - b2.startRow || b1.startCol - b2.startCol,
    );
    const run = { ...sorted[0] };
    for (const { startRow, startCol, endCol } of sorted.slice(1)) {
        if (startRow !== run.startRow || startCol !== run.endCol) {
            break;
        }
        run.endCol = endCol;
    }
    return run;
}

/**
 * @param {(number | string)[]} coarseRowKeys
 * @param {number[]} gridRows
 * @returns {string}
 */
export function rowsTemplate(coarseRowKeys, gridRows) {
    const template = [];
    for (let i = 0; i < coarseRowKeys.length - 1; i++) {
        const x = +coarseRowKeys[i];
        const y = +coarseRowKeys[i + 1];
        const height = gridRows.slice(x - 1, y - 1).reduce((a, b) => a + b, 0);
        template.push(`[r${x}]${height}px`);
    }
    template.push(`[r${coarseRowKeys.at(-1)}]`);
    return template.join("");
}

/**
 * @param {Object} params
 * @param {number} params.contentWidth
 * @param {number} params.rowHeaderWidth
 * @param {number} params.cellPart
 * @param {number} params.minimalColumnWidth
 * @param {number} params.columnCount
 * @param {number} params.foldedGridColumnCount
 * @param {(0 | 1)[]} [params.foldedColumns]
 * @returns {{ visibleCellContainerWidth: number, cellPartWidth: number, columnWidth: number, columnWidths: number[], totalWidth: number | null }}
 */
export function columnWidths({
    contentWidth,
    rowHeaderWidth,
    cellPart,
    minimalColumnWidth,
    columnCount,
    foldedGridColumnCount,
    foldedColumns,
}) {
    const visibleCellContainerWidth = contentWidth - rowHeaderWidth;
    if (foldedGridColumnCount === 1) {
        const cellPartWidth = Math.floor(visibleCellContainerWidth / cellPart);
        const columnWidth = cellPartWidth * cellPart;
        return {
            visibleCellContainerWidth,
            cellPartWidth,
            columnWidth,
            columnWidths: [columnWidth],
            totalWidth: null,
        };
    }
    const hiddenColumnsCount = foldedColumns?.filter(Boolean).length || 0;
    const foldedColumnsCount = foldedGridColumnCount + hiddenColumnsCount - columnCount;
    const sharedWidth = Math.floor(
        (visibleCellContainerWidth - FOLDED_COLUMN_WIDTH * foldedColumnsCount) /
            (foldedGridColumnCount - foldedColumnsCount),
    );
    const cellPartWidth = Math.floor(
        Math.max(sharedWidth, minimalColumnWidth) / cellPart,
    );
    const columnWidth = cellPartWidth * cellPart;
    const widths = foldedColumns
        ? foldedRuns(foldedColumns).map((run) =>
              run.folded ? FOLDED_COLUMN_WIDTH : columnWidth,
          )
        : new Array(foldedGridColumnCount).fill(columnWidth);
    const overflows = sharedWidth <= minimalColumnWidth;
    return {
        visibleCellContainerWidth,
        cellPartWidth,
        columnWidth,
        columnWidths: widths,
        totalWidth: overflows
            ? widths.reduce((sum, w) => sum + w, 0) + rowHeaderWidth
            : null,
    };
}

/**
 * @param {(number | string)[]} coarseColKeys
 * @param {(from: number, to: number) => { distance: number, flexible: boolean }} distanceBetween
 * @returns {string}
 */
export function colsTemplate(coarseColKeys, distanceBetween) {
    const template = [];
    for (let i = 0; i < coarseColKeys.length - 1; i++) {
        const x = +coarseColKeys[i];
        const y = +coarseColKeys[i + 1];
        const { distance, flexible } = distanceBetween(x, y);
        template.push(`[c${x}]minmax(${distance}px,${+flexible}fr)`);
    }
    template.push(`[c${coarseColKeys.at(-1)}]`);
    return template.join("");
}

/**
 * @param {number} x
 * @param {Object} params
 * @param {number} params.cellContainerWidth
 * @param {number[]} params.columnWidths
 * @param {number} params.columnCount
 * @param {(index: number) => number} params.indexInTotalGrid
 * @returns {number}
 */
export function focusFactorAt(
    x,
    { cellContainerWidth, columnWidths, columnCount, indexInTotalGrid },
) {
    if (columnWidths.length === columnCount) {
        return x / cellContainerWidth;
    }
    let sum = 0;
    for (let i = 0; i < columnWidths.length; i++) {
        sum += columnWidths[i];
        if (sum > x) {
            return (indexInTotalGrid(i) + 1) / columnCount;
        }
    }
    return x / cellContainerWidth;
}

/**
 * @param {number} start
 * @param {number} stop
 * @param {Object} params
 * @param {number} params.cellPart
 * @param {number} params.cellPartWidth
 * @param {number[]} [params.foldedGridColumnSpans]
 * @param {(0 | 1)[]} [params.foldedColumns]
 * @param {(col: number) => number} params.colNumberInFoldedGrid
 * @param {(index: number) => number} params.indexInTotalGrid
 * @returns {{ distance: number, flexible: boolean }}
 */
export function subColumnsDistance(
    start,
    stop,
    {
        cellPart,
        cellPartWidth,
        foldedGridColumnSpans,
        foldedColumns,
        colNumberInFoldedGrid,
        indexInTotalGrid,
    },
) {
    if (!foldedGridColumnSpans) {
        return { distance: (stop - start) * cellPartWidth, flexible: true };
    }
    let distance = 0;
    let flexible = true;
    for (let j = colNumberInFoldedGrid(start); j < colNumberInFoldedGrid(stop); j++) {
        if (foldedColumns[indexInTotalGrid(Math.floor((j - 1) / cellPart))]) {
            distance += FOLDED_COLUMN_WIDTH / cellPart;
            if (foldedGridColumnSpans.length > 1) {
                flexible = false;
            }
        } else {
            distance += cellPartWidth;
        }
    }
    return { distance, flexible };
}
