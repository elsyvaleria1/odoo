// @ts-check

import { describe, expect, test } from "@odoo/hoot";
import { Component, EventBus, useProps, xml } from "@odoo/owl";
import { mountWithCleanup } from "@web/../tests/web_test_helpers";
import { ModelEvent } from "@web/core/events";
import { useListKeyboardNavigation } from "@web/views/list/list_keyboard_nav";

describe.current.tags("desktop");

/** @param {Record<string, any>} [overrides] */
/**
 * @param {Record<string, any>} [overrides]
 * @returns {any}
 */
function makeCtx(overrides = {}) {
    const props = {
        list: {
            model: { multiEdit: false, useSampleModel: false, bus: new EventBus() },
        },
    };
    return {
        getColumns: () => /** @type {any[]} */ ([]),
        getProps: () => props,
        getSearchModel: () => undefined,
        getGridState: () => /** @type {any} */ (null),
        onToggleGroup: () => {},
        toggleRecordSelection: () => {},
        onOpenRecord: () => {},
        onDeleteRecord: () => {},
        isInlineEditable: () => false,
        expandCheckboxes: () => false,
        getSel: () => /** @type {any} */ (null),
        getVirtualization: () => /** @type {any} */ (null),
        findFocusFutureCell: null,
        ...overrides,
    };
}

const ROWS = `
    <tbody>
        <tr data-row-index="0">
            <td data-col-index="0" class="o_data_cell"><input class="r0c0"/></td>
            <td data-col-index="1" class="o_data_cell"><input class="r0c1"/></td>
        </tr>
        <tr data-row-index="1">
            <td data-col-index="0" class="o_data_cell"><input class="r1c0"/></td>
            <td data-col-index="1" class="o_data_cell"><input class="r1c1"/></td>
        </tr>
    </tbody>`;

/**
 * @param {Record<string, any>} [ctxOverrides]
 * @param {string} [rows]
 * @returns {Promise<{ nav: any, table: HTMLTableElement, cell: (s: string) => any }>}
 */
async function mountNav(ctxOverrides = {}, rows = ROWS) {
    /** @type {any} */
    let nav = null;
    /** @type {any} */
    let tableEl = null;
    class Host extends Component {
        static template = xml`<table>${rows}</table>`;
        static props = {};
        props = useProps(this.constructor.props);
        setup() {
            const tableRef = {
                get el() {
                    return tableEl;
                },
            };
            nav = useListKeyboardNavigation(tableRef, makeCtx(ctxOverrides));
        }
    }
    await mountWithCleanup(Host);
    tableEl = document.querySelector("table");
    return {
        nav,
        table: tableEl,
        cell: (selector) => tableEl.querySelector(selector),
    };
}

/** @param {Record<string, any>} [overrides] */
function gridStateStub(overrides = {}) {
    return {
        steps: /** @type {any[]} */ ([]),
        moveFocus(
            /** @type {any} */ rowIndex,
            /** @type {any} */ colIndex,
            /** @type {any} */ direction,
        ) {
            this.steps.push(["moveFocus", rowIndex, colIndex, direction]);
            return { rowIndex: 1, colIndex: 0 };
        },
        rowAt: () => ({ type: "record" }),
        rememberColumn() {},
        findRowByRecordId: () => /** @type {any} */ (null),
        flatRows: /** @type {any[]} */ ([]),
        ...overrides,
    };
}

describe("field dirtiness", () => {
    test("lastIsDirty stays set while any owner is still dirty", async () => {
        const bus = new EventBus();
        const props = {
            list: { model: { multiEdit: false, useSampleModel: false, bus } },
        };
        const { nav } = await mountNav({ getProps: () => props });
        const first = Symbol("first");
        const second = Symbol("second");
        bus.trigger(ModelEvent.FIELD_IS_DIRTY, { id: first, isDirty: true });
        bus.trigger(ModelEvent.FIELD_IS_DIRTY, { id: second, isDirty: true });
        bus.trigger(ModelEvent.FIELD_IS_DIRTY, { id: first, isDirty: false });
        expect(nav.lastIsDirty).toBe(true);
        bus.trigger(ModelEvent.FIELD_IS_DIRTY, { id: second, isDirty: false });
        expect(nav.lastIsDirty).toBe(false);
    });
});

describe("findFocusMove — with a grid state", () => {
    test("asks the grid state to move from the cell's own coordinates", async () => {
        const grid = gridStateStub();
        const { nav, cell } = await mountNav({ getGridState: () => grid });

        const move = nav.findFocusMove(cell(`[data-row-index="0"] td`), false, "down");

        expect(grid.steps).toEqual([["moveFocus", 0, 0, "down"]]);
        expect(move.el).toBe(cell(".r1c0"));
    });

    test("reads the column from data-col-index, not from the child position", async () => {
        const grid = gridStateStub();
        const { nav, cell } = await mountNav({ getGridState: () => grid });

        nav.findFocusMove(
            cell(`[data-row-index="0"] [data-col-index="1"]`),
            false,
            "up",
        );

        expect(grid.steps).toEqual([["moveFocus", 0, 1, "up"]]);
    });

    test("a grid state that refuses the move falls through to the DOM walk", async () => {
        const grid = gridStateStub({ moveFocus: () => /** @type {any} */ (null) });
        const { nav, cell } = await mountNav({ getGridState: () => grid });

        const move = nav.findFocusMove(cell(`[data-row-index="0"] td`), false, "down");

        expect(move.el).toBe(cell(".r1c0"));
    });
});

describe("findFocusMove — cells that cannot take focus", () => {
    const GAPPED_ROWS = `
        <tbody>
            <tr>
                <td><input class="a0"/></td>
                <td class="gap"/>
                <td><input class="a2"/></td>
            </tr>
            <tr class="blank"><td/><td/><td/></tr>
            <tr>
                <td><input class="c0"/></td>
                <td><input class="c1"/></td>
                <td class="gap"/>
            </tr>
        </tbody>
        <tfoot>
            <tr><td/><td/><td><button class="foot"/></td></tr>
        </tfoot>`;

    test("left and right skip every cell that holds nothing focusable", async () => {
        const { nav, cell } = await mountNav({}, GAPPED_ROWS);

        expect(nav.findFocusMove(cell(".a0").parentElement, false, "right").el).toBe(
            cell(".a2"),
        );
        expect(nav.findFocusMove(cell(".a2").parentElement, false, "left").el).toBe(
            cell(".a0"),
        );
        expect(nav.findFocusMove(cell(".c1").parentElement, false, "right")).toBe(null);
    });

    test("up and down pass through a row with nothing focusable", async () => {
        const { nav, cell } = await mountNav({}, GAPPED_ROWS);

        expect(nav.findFocusMove(cell(".a0").parentElement, false, "down").el).toBe(
            cell(".c0"),
        );
        expect(nav.findFocusMove(cell(".c0").parentElement, false, "up").el).toBe(
            cell(".a0"),
        );
    });

    test("up and down land on the nearest focusable cell of a row", async () => {
        const { nav, cell } = await mountNav({}, GAPPED_ROWS);

        expect(nav.findFocusMove(cell(".c1").parentElement, false, "up").el).toBe(
            cell(".a0"),
        );
    });

    test("the footer is reached only by an exact hit", async () => {
        const { nav, cell } = await mountNav({}, GAPPED_ROWS);

        expect(nav.findFocusMove(cell(".c1").parentElement, false, "down")).toBe(null);
        expect(
            nav.findFocusMove(cell(".c1").closest("tr").lastElementChild, false, "down")
                .el,
        ).toBe(cell(".foot"));
    });
});

describe("findFocusMove — the virtualization handover", () => {
    function offscreenGrid() {
        return gridStateStub({
            moveFocus: () => ({ rowIndex: 99, colIndex: 0 }),
            flatRows: { 99: { type: "record", record: { id: 42 } } },
        });
    }

    test("defers to virtualization instead of returning an element", async () => {
        /** @type {any[]} */
        const ensured = [];
        const { nav, cell } = await mountNav({
            getGridState: offscreenGrid,
            getVirtualization: () => ({
                isActive: true,
                scrollRowIntoView: (/** @type {any} */ i) => ensured.push(i),
            }),
        });

        const move = nav.findFocusMove(cell(`[data-row-index="0"] td`), false, "down");

        expect(move).toEqual({ pending: true });
        expect(ensured).toEqual([99]);
        expect(nav.pendingVirtFocus).toEqual({
            rowIndex: 99,
            colIndex: 0,
            recordId: "42",
        });
    });

    test("without an active virtualization there is no pending focus", async () => {
        const { nav, cell } = await mountNav({
            getGridState: offscreenGrid,
            getVirtualization: () => ({ isActive: false, scrollRowIntoView: () => {} }),
        });

        nav.findFocusMove(cell(`[data-row-index="0"] td`), false, "down");

        expect(nav.pendingVirtFocus).toBe(null);
    });

    test("resolveArrowMove reports a pending move as handled and stamps its origin", async () => {
        const { nav, cell } = await mountNav({
            getGridState: offscreenGrid,
            getVirtualization: () => ({ isActive: true, scrollRowIntoView: () => {} }),
        });
        const origin = cell(`[data-row-index="0"] td`);

        expect(nav.resolveArrowMove(origin, false, "down")).toBe(true);
        expect(nav.pendingVirtFocus.origin).toEqual({
            cell: origin,
            cellIsInGroupRow: false,
            direction: "down",
        });
    });
});

describe("resolvePendingVirtFocus", () => {
    /** @param {Record<string, any>} [gridOverrides] */
    async function pending(gridOverrides = {}) {
        const grid = gridStateStub({
            moveFocus: () => ({ rowIndex: 99, colIndex: 0 }),
            flatRows: { 99: { type: "record", record: { id: 42 } } },
            ...gridOverrides,
        });
        const { nav, cell } = await mountNav({
            getGridState: () => grid,
            getVirtualization: () => ({ isActive: true, scrollRowIntoView: () => {} }),
        });
        nav.findFocusMove(cell(`[data-row-index="0"] td`), false, "down");
        expect(nav.pendingVirtFocus).not.toBe(null);
        return { nav, grid, cell };
    }

    test("drops the pending focus when the record no longer exists", async () => {
        const { nav } = await pending({
            findRowByRecordId: () => /** @type {any} */ (null),
        });
        nav.resolvePendingVirtFocus();
        expect(nav.pendingVirtFocus).toBe(null);
    });

    test("retries while the row stays unrendered, then gives up at the cap", async () => {
        const { nav } = await pending({
            findRowByRecordId: () => ({ globalIndex: 99 }),
        });
        for (let i = 0; i < 20; i++) {
            nav.resolvePendingVirtFocus();
        }
        expect(nav.pendingVirtFocus).not.toBe(null, {
            message: "still pending at the cap",
        });
        nav.resolvePendingVirtFocus();
        expect(nav.pendingVirtFocus).toBe(null, {
            message: "and dropped on the attempt past it",
        });
    });

    test("focuses and clears once the row is rendered", async () => {
        const { nav, cell } = await pending({
            findRowByRecordId: () => ({ globalIndex: 1 }),
        });
        nav.resolvePendingVirtFocus();
        expect(document.activeElement).toBe(cell(".r1c0"));
        nav.resolvePendingVirtFocus();
        expect(nav.pendingVirtFocus).toBe(null);
    });

    test("clearPendingVirtFocus drops it outright", async () => {
        const { nav } = await pending();
        nav.clearPendingVirtFocus();
        expect(nav.pendingVirtFocus).toBe(null);
    });
});

describe("the published members are the seam", () => {
    test("replacing resolveArrowMove reaches onCellKeydownReadOnlyMode", async () => {
        const { nav, cell } = await mountNav();
        /** @type {any[]} */
        const calls = [];
        const original = nav.resolveArrowMove;
        nav.resolveArrowMove = (/** @type {any[]} */ ...args) => {
            calls.push(args[2]);
            return original(...args);
        };

        nav.onCellKeydownReadOnlyMode(
            "arrowdown",
            cell(`[data-row-index="0"] td`),
            null,
            null,
        );

        expect(calls).toEqual(["down"]);
    });

    test("replacing findFocusMove reaches resolveArrowMove", async () => {
        const { nav, cell } = await mountNav();
        let reached = 0;
        nav.findFocusMove = /** @type {() => any} */ (
            () => {
                reached++;
                return null;
            }
        );

        nav.resolveArrowMove(cell(`[data-row-index="0"] td`), false, "up");

        expect(reached).toBe(1);
    });
});
