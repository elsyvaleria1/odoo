/** @odoo-module native */
import { compareDates, endOf, maxDate, minDate, startOf } from "@web/core/l10n/dates";

import { localEndOf, localStartOf } from "./gantt_helpers.js";

/**
 * @typedef {Temporal.ZonedDateTime} DateTime
 * @typedef {import("./gantt_grid_geometry").GridGeometry} GridGeometry
 * @typedef {import("./gantt_ranges").Scale} Scale
 */

/**
 * @param {Object} params
 * @param {number} params.firstIndex
 * @param {number} params.lastIndex
 * @param {number} params.columnCount
 * @param {Scale} params.scale
 * @param {DateTime} params.globalStart
 * @param {DateTime} params.globalStop
 * @param {boolean} params.displayUnavailability
 * @param {number[]} [params.foldedGridColumnSpans]
 * @param {(0 | 1)[]} [params.foldedColumns]
 * @param {Record<number, { stopIndex?: number }>} [params.foldableColumnsMapping]
 * @param {(index: number) => number} params.indexInTotalGrid
 * @param {GridGeometry} params.geometry
 * @param {DateTime} params.now
 */
function columnAt(
    j,
    {
        cellPart,
        nowStart,
        nowEnd,
        displayUnavailability,
        foldedGridColumnSpans,
        foldedColumns,
        foldableColumnsMapping,
        indexInTotalGrid,
        geometry,
    },
) {
    const columnIndex = indexInTotalGrid(j);
    const col = columnIndex * cellPart + 1;
    const { start, stop } = geometry.columnFromColNumber(col);
    const span = foldedGridColumnSpans?.[j] || 1;
    const column = {
        index: columnIndex,
        grid: { column: [col, col + cellPart] },
        start,
        stop,
    };
    if (compareDates(nowStart, start) <= 0 && compareDates(start, nowEnd) <= 0) {
        column.isToday = true;
    }
    if (foldedColumns?.[columnIndex]) {
        column.stop = geometry.columnFromColNumber(col + (span - 1) * cellPart).stop;
        column.isFolded = true;
        column.grid.column[1] = col + span * cellPart;
    }
    if (displayUnavailability) {
        const foldableGroup = foldableColumnsMapping[columnIndex];
        column.isFoldable = foldableGroup
            ? foldableGroup.stopIndex === columnIndex + span - 1
                ? "stop"
                : 1
            : 0;
    }
    return column;
}

function columnGroupAt(
    groupStart,
    column,
    { unit, groupsLeftBound, groupsRightBound, geometry },
) {
    const [groupFirstCol, groupLastCol] = geometry.gridColumnFromDates(
        maxDate(groupsLeftBound, groupStart),
        minDate(groupsRightBound, localEndOf(groupStart, unit)),
    );
    return {
        grid: { column: [groupFirstCol, groupLastCol] },
        start: groupStart,
        isFolded: column.index === 0 && groupLastCol < column.grid.column[1],
    };
}

export function visibleColumns(params) {
    const { firstIndex, lastIndex, columnCount, scale, globalStart, globalStop } =
        params;
    const { indexInTotalGrid, geometry, now } = params;
    const { cellPart, interval, unit } = scale;
    const columns = [];
    const subColumns = [];
    const columnsGroups = [];
    const coarseGridCols = { 1: true, [columnCount * cellPart + 1]: true };

    const columnParams = {
        ...params,
        cellPart,
        nowStart: startOf(now, interval),
        nowEnd: endOf(now, interval),
    };
    const groupParams = {
        unit,
        geometry,
        groupsLeftBound: maxDate(
            globalStart,
            localStartOf(
                globalStart.add({ [`${interval}s`]: indexInTotalGrid(firstIndex) }),
                unit,
            ),
        ),
        groupsRightBound: minDate(
            localEndOf(
                globalStart.add({ [`${interval}s`]: indexInTotalGrid(lastIndex) }),
                unit,
            ),
            globalStop,
        ),
    };

    let currentGroup = null;
    for (let j = firstIndex; j <= lastIndex; j++) {
        const column = columnAt(j, columnParams);
        const [col] = column.grid.column;
        if (column.isFolded) {
            coarseGridCols[col] = true;
        } else {
            for (let i = 0; i < cellPart; i++) {
                subColumns.push({
                    ...geometry.subColumnFromColNumber(col + i),
                    isToday: Boolean(column.isToday),
                    columnIndex: column.index,
                });
                coarseGridCols[col + i] = true;
            }
        }
        columns.push(column);

        const groupStart = localStartOf(column.start, unit);
        if (!currentGroup || !groupStart.equals(currentGroup.start)) {
            currentGroup = columnGroupAt(groupStart, column, groupParams);
            columnsGroups.push(currentGroup);
            coarseGridCols[currentGroup.grid.column[0]] = true;
            coarseGridCols[currentGroup.grid.column[1]] = true;
        }
        if (j === lastIndex && currentGroup.grid.column[1] < column.grid.column[1]) {
            columnsGroups.push({
                grid: { column: [currentGroup.grid.column[1], column.grid.column[1]] },
                isFolded: true,
            });
        }
    }
    return { columns, subColumns, columnsGroups, coarseGridCols };
}
