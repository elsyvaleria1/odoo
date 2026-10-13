/** @odoo-module native */
import { compareDates, endOf, startOf } from "@web/core/l10n/dates";

import { dateAddFixedOffset, diffColumn } from "./gantt_helpers.js";

/**
 * @typedef {Temporal.ZonedDateTime} DateTime
 * @typedef {import("./gantt_ranges").Scale} Scale
 */

export class GridGeometry {
    /**
     * @param {DateTime} globalStart
     * @param {Scale} scale
     */
    constructor(globalStart, scale) {
        this.globalStart = globalStart;
        this.scale = scale;
        this.columnByCol = new Map();
        this.subColumnByCol = new Map();
        this.indexByColumnStart = new Map();
        this.subCellStartsByColumnStart = new Map();
    }

    /**
     * @param {DateTime} column
     * @returns {number}
     */
    columnIndexFromDate(column) {
        let index = this.indexByColumnStart.get(column.epochMilliseconds);
        if (index === undefined) {
            index = diffColumn(this.globalStart, column, this.scale.interval);
            this.indexByColumnStart.set(column.epochMilliseconds, index);
        }
        return index;
    }

    /**
     * @param {DateTime} startDate
     * @param {DateTime} stopDate
     * @returns {[number, number]}
     */
    gridColumnFromDates(startDate, stopDate) {
        const { cellPart } = this.scale;
        const { column: column1, delta: delta1 } = this.subColumnFromDate(startDate);
        const { column: column2, delta: delta2 } = this.subColumnFromDate(
            stopDate,
            false,
        );
        const index1 = this.columnIndexFromDate(column1);
        const index2 = this.columnIndexFromDate(column2);
        const firstCol = 1 + index1 * cellPart + delta1;
        const span = (index2 - index1) * cellPart + delta2 - delta1;
        return [firstCol, firstCol + span];
    }

    /**
     * @param {DateTime} column
     * @returns {DateTime[]}
     */
    subCellStarts(column) {
        let starts = this.subCellStartsByColumnStart.get(column.epochMilliseconds);
        if (!starts) {
            const { cellPart, cellTime, time } = this.scale;
            starts = [column];
            for (let i = 1; i < cellPart; i++) {
                starts.push(dateAddFixedOffset(column, { [time]: i * cellTime }));
            }
            this.subCellStartsByColumnStart.set(column.epochMilliseconds, starts);
        }
        return starts;
    }

    /**
     * @param {DateTime} date
     * @param {boolean} [onLeft=true]
     * @returns {{ column: DateTime, delta: number }}
     */
    subColumnFromDate(date, onLeft = true) {
        const { interval, cellPart } = this.scale;
        const column = startOf(date, interval);
        const starts = this.subCellStarts(column);
        let delta;
        if (onLeft) {
            delta = 0;
            for (let i = 1; i < cellPart; i++) {
                if (compareDates(starts[i], date) <= 0) {
                    delta += 1;
                } else {
                    break;
                }
            }
        } else {
            delta = cellPart;
            for (let i = cellPart - 1; i >= 0; i--) {
                if (compareDates(starts[i], date) >= 0) {
                    delta -= 1;
                } else {
                    break;
                }
            }
        }
        return { column, delta };
    }

    /**
     * @param {number} col
     * @returns {{ start: DateTime, stop: DateTime }}
     */
    subColumnFromColNumber(col) {
        let subColumn = this.subColumnByCol.get(col);
        if (!subColumn) {
            const { interval, cellPart, cellTime, time } = this.scale;
            const delta = (col - 1) % cellPart;
            const start = this.globalStart.add({
                [`${interval}s`]: this.columnIndexFromColNumber(col),
            });
            subColumn = {
                start: dateAddFixedOffset(start, { [time]: delta * cellTime }),
                stop: dateAddFixedOffset(start, {
                    [time]: (delta + 1) * cellTime,
                    seconds: -1,
                }),
            };
            this.subColumnByCol.set(col, subColumn);
        }
        return subColumn;
    }

    /**
     * @param {number} col
     * @returns {number}
     */
    columnIndexFromColNumber(col) {
        const { cellPart } = this.scale;
        const delta = (col - 1) % cellPart;
        return (col - 1 - delta) / cellPart;
    }

    /**
     * @param {number} col
     * @returns {{ start: DateTime, stop: DateTime }}
     */
    columnFromColNumber(col) {
        let column = this.columnByCol.get(col);
        if (!column) {
            const { interval } = this.scale;
            const start = this.globalStart.add({
                [`${interval}s`]: this.columnIndexFromColNumber(col),
            });
            column = { start, stop: endOf(start, interval) };
            this.columnByCol.set(col, column);
        }
        return column;
    }
}
