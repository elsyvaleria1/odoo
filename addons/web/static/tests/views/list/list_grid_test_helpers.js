// @ts-check

import { expect } from "@odoo/hoot";
import { queryAll } from "@odoo/hoot-dom";

/**
 * @typedef {{ span: number, misplaced: string[] }} RowLayout
 */

/**
 * @param {Element} cell
 * @returns {boolean}
 */
function isLaidOut(cell) {
    return getComputedStyle(cell).display !== "none";
}

/**
 * For every body row matched by `rows` inside `table`: how many header columns
 * it covers, and which single-width named cells do not start under the header
 * cell of the same name. A cell the browser does not lay out covers nothing.
 *
 * @param {{ table?: string, rows?: string }} [options]
 * @returns {RowLayout[]}
 */
export function getListRowLayouts({
    table = ".o_list_table",
    rows = ".o_data_row",
} = {}) {
    const headerCells = queryAll(`${table} thead tr th`).filter(isLaidOut);
    const headerIndex = Object.fromEntries(
        headerCells
            .map((th, index) => [th.getAttribute("data-name"), index])
            .filter(([name]) => name),
    );
    const rowSelector = rows
        .split(",")
        .map((selector) => `${table} tbody ${selector.trim()}`)
        .join(", ");
    return queryAll(rowSelector).map((row) => {
        let start = 0;
        const misplaced = [];
        for (const cell of row.children) {
            if (!isLaidOut(cell)) {
                continue;
            }
            const name = cell.getAttribute("name");
            const colspan = Number(cell.getAttribute("colspan") || 1);
            if (
                name &&
                name in headerIndex &&
                colspan === 1 &&
                headerIndex[name] !== start
            ) {
                misplaced.push(`${name}@${start}!=${headerIndex[name]}`);
            }
            start += colspan;
        }
        return { span: start, misplaced };
    });
}

/**
 * Every matched row spans exactly the header's column grid and puts each named
 * cell under its own header cell; at least one row must match.
 *
 * @param {{ table?: string, rows?: string }} [options]
 */
export function expectRowsCoverHeaderGrid(options = {}) {
    const table = options.table ?? ".o_list_table";
    const headerCount = queryAll(`${table} thead tr th`).filter(isLaidOut).length;
    const layouts = getListRowLayouts(options);
    expect(layouts.length).toBeGreaterThan(0);
    expect(layouts).toEqual(layouts.map(() => ({ span: headerCount, misplaced: [] })));
}
