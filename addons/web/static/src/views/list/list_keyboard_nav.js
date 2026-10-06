// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";
import { SearchModelEvent } from "@web/core/events";
import { getTabableElements } from "@web/core/utils/dom/ui";
import { useBus } from "@web/core/utils/hooks";
import { useFieldDirtyOwners } from "@web/views/view_hook";

import {
    findNextFocusableOnRow,
    findPreviousFocusableOnRow,
    focusAndSelect,
    getElementToFocus,
    getFocusableInCell,
    togglesFocusInsideCell,
} from "./list_focus.js";
import { makeEditHandlers } from "./list_keyboard_edit.js";

const MAX_VIRT_FOCUS_RETRIES = 20;
const log = makeLogger("web.view.list");

/** @typedef {"up" | "down" | "left" | "right"} Direction */

/**
 * @param {Element} row
 * @param {number} colIndex
 * @param {"left" | "right"} [direction]
 * @returns {Element | null}
 */
function nearestCellOnRow(row, colIndex, direction) {
    if (direction !== "left" && direction !== "right") {
        return null;
    }
    const cells = [...row.querySelectorAll("[data-col-index]")].map((cell) => ({
        cell,
        index: Number.parseInt(
            /** @type {string} */ (cell.getAttribute("data-col-index")),
            10,
        ),
    }));
    const reachable = cells.filter((c) =>
        direction === "left" ? c.index <= colIndex : c.index >= colIndex,
    );
    if (!reachable.length) {
        return null;
    }
    return reachable.reduce((best, c) =>
        Math.abs(c.index - colIndex) < Math.abs(best.index - colIndex) ? c : best,
    ).cell;
}

/**
 * @param {Element} row
 * @param {"up" | "down"} direction
 * @returns {Element | null | undefined}
 */
function adjacentRow(row, direction) {
    if (direction === "up") {
        return (
            row.previousElementSibling ||
            row.parentElement.previousElementSibling?.lastElementChild
        );
    }
    return (
        row.nextElementSibling ||
        row.parentElement.nextElementSibling?.firstElementChild
    );
}

/**
 * @param {Element | null | undefined} row
 * @returns {boolean}
 */
function isNavigableRow(row) {
    // the footer holds no per-column control: only an exact hit may land there
    return Boolean(row) && row.parentElement?.tagName !== "TFOOT";
}

/**
 * @param {Element} cell
 * @returns {HTMLElement | null}
 */
function focusableNearCell(cell) {
    const direct = getFocusableInCell(cell);
    if (direct) {
        return direct;
    }
    const siblings = [...cell.parentElement.children];
    const index = siblings.indexOf(cell);
    let nearest = null;
    let nearestIndex = -1;
    for (const [i, sibling] of siblings.entries()) {
        if (
            i !== index &&
            (!nearest || Math.abs(i - index) < Math.abs(nearestIndex - index))
        ) {
            const focusable = getFocusableInCell(sibling);
            if (focusable) {
                nearest = focusable;
                nearestIndex = i;
            }
        }
    }
    log.logic("arrow.nearestOnRow", () => ({
        cellIndex: index,
        landedIndex: nearest ? nearestIndex : null,
    }));
    return nearest;
}

/**
 * @param {Element} cell
 * @param {"up" | "down"} direction
 * @returns {HTMLElement | null}
 */
function focusableInColumnFrom(cell, direction) {
    if (!isNavigableRow(cell.parentElement)) {
        return getFocusableInCell(cell);
    }
    const focusable = focusableNearCell(cell);
    if (focusable) {
        return focusable;
    }
    const index = [...cell.parentElement.children].indexOf(cell);
    let row = adjacentRow(cell.parentElement, direction);
    let passedRows = 1;
    while (isNavigableRow(row)) {
        const candidate = row.children[Math.min(index, row.children.length - 1)];
        const found = candidate && focusableNearCell(candidate);
        if (found) {
            log.logic("arrow.passThrough", () => ({ direction, index, passedRows }));
            return found;
        }
        row = adjacentRow(row, direction);
        passedRows++;
    }
    log.logic("arrow.passThrough", () => ({
        direction,
        index,
        passedRows,
        exhausted: true,
    }));
    return null;
}

/**
 * @param {Element} row
 * @param {number} index
 * @param {{
 * direction: "up" | "down",
 * cellIsInGroupRow: boolean,
 * lastKnownIndex: number,
 * isHeaderRow: boolean,
 * }} params
 * @returns {{ cell: Element | undefined, lastKnownIndex: number,
 * rememberColumn?: number } | undefined}
 */
function verticalNeighbourCell(
    row,
    index,
    { direction, cellIsInGroupRow, lastKnownIndex, isHeaderRow },
) {
    const futureRow = adjacentRow(row, direction);
    if (!futureRow) {
        return undefined;
    }
    const addCell = [...futureRow.children].find((c) =>
        c.classList.contains("o_group_field_row_add"),
    );
    const nextIsGroup = futureRow.classList.contains("o_group_header");
    const rowTypeSwitched = cellIsInGroupRow !== nextIsGroup;
    const isGroupToGroup = cellIsInGroupRow && nextIsGroup;

    let targetIndex;
    if (rowTypeSwitched || isGroupToGroup) {
        targetIndex = lastKnownIndex || 0;
    } else {
        lastKnownIndex = index;
    }
    let rememberColumn;
    if (direction === "down" && isHeaderRow) {
        lastKnownIndex = index;
        rememberColumn = index;
    }
    const defaultIndex = cellIsInGroupRow ? targetIndex : 0;
    return {
        cell: addCell || futureRow.children[rowTypeSwitched ? defaultIndex : index],
        lastKnownIndex,
        rememberColumn,
    };
}

/**
 * @param {HTMLTableCellElement} cell
 * @param {1 | -1} step
 * @returns {Element | null}
 */
function adjacentGroupButton(cell, step) {
    const buttons = Array.from(cell.querySelectorAll(".o_group_buttons button"));
    const currentButton = document.activeElement.closest("button");
    return buttons[buttons.indexOf(currentButton) + step] || currentButton;
}

/**
 * @param {any} tableRef
 * @param {{ rowIndex: number, colIndex: number }} position
 * @param {"left" | "right"} [direction]
 * @returns {{ rendered: false } | { rendered: true, cell: Element | null, addLine: HTMLElement | null }}
 */
function cellAtPosition(tableRef, { rowIndex, colIndex }, direction) {
    const row = tableRef.el.querySelector(`[data-row-index="${rowIndex}"]`);
    if (!row) {
        return { rendered: false };
    }
    const addLineCell = row.querySelector(".o_group_field_row_add");
    if (addLineCell) {
        const addLine = getFocusableInCell(addLineCell);
        log.logic("focusAtPosition.addLine", () => ({
            rowIndex,
            focusable: addLine?.tagName ?? null,
        }));
        return { rendered: true, cell: addLineCell, addLine };
    }
    const cell =
        row.querySelector(`[data-col-index="${colIndex}"]`) ||
        nearestCellOnRow(row, colIndex, direction) ||
        row.children[Math.min(colIndex, row.children.length - 1)] ||
        null;
    return { rendered: true, cell, addLine: null };
}

/**
 * @param {ReturnType<typeof cellAtPosition>} target
 * @param {{ rowIndex: number, colIndex: number }} position
 * @returns {HTMLElement | null}
 */
function focusableAtTarget(target, position) {
    if (!target.rendered || !target.cell) {
        return null;
    }
    if (target.addLine) {
        return target.addLine;
    }
    const focusable = focusableNearCell(target.cell);
    if (!focusable) {
        log.logic("focusAtPosition.unfocusableCell", () => ({
            ...position,
            cell: target.cell.className,
        }));
    }
    return focusable;
}

/**
 * @typedef {Pick<
 * import("./list_renderer").ListGridContext,
 * | "getColumns"
 * | "getProps"
 * | "getSearchModel"
 * | "getGridState"
 * | "onToggleGroup"
 * | "toggleRecordSelection"
 * | "onOpenRecord"
 * | "onDeleteRecord"
 * | "isInlineEditable"
 * | "expandCheckboxes"
 * | "getSel"
 * | "getVirtualization"
 * | "findFocusFutureCell"
 * | "setKeyboardNavigation"
 * > & import("./list_keyboard_edit").ListEditContext} ListKeyboardContext
 */

class ListKeyboardNavigation {
    /** @type {{ column: any, record: any } | null} */
    lastEditedCell = null;
    /** @type {{ column: any, record: any, forward?: boolean } | null} */
    cellToFocus = null;
    lastIsDirty = false;
    /**
     * @type {{
     * cell: HTMLTableCellElement,
     * cellIsInGroupRow: boolean,
     * direction: string,
     * move: { el: HTMLElement } | { pending: true } | null,
     * } | null}
     */
    _latchedMove = null;
    _lastKnownIndex = 0;
    /** @type {{ rowIndex: number, colIndex: number, recordId?: string, retries?: number, origin?: { cell: HTMLTableCellElement, cellIsInGroupRow: boolean, direction: "up" | "down" | "left" | "right" } } | null} */
    _pendingVirtFocus = null;

    /**
     * @param {any} tableRef
     * @param {ListKeyboardContext} ctx
     */
    constructor(tableRef, ctx) {
        this.tableRef = tableRef;
        this.ctx = ctx;
        // every method is bound: a renderer replaces one on the instance and
        // the seam tests call the captured original detached
        const proto = ListKeyboardNavigation.prototype;
        for (const name of Object.getOwnPropertyNames(proto)) {
            const descriptor = Object.getOwnPropertyDescriptor(proto, name);
            if (name !== "constructor" && typeof descriptor.value === "function") {
                this[name] = proto[name].bind(this);
            }
        }
    }

    get pendingVirtFocus() {
        return this._pendingVirtFocus;
    }

    /** @param {HTMLElement} el */
    focus(el) {
        focusAndSelect(el);
    }

    /**
     * @param {HTMLTableCellElement} cell
     * @param {boolean} cellIsInGroupRow
     * @param {"up" | "down" | "left" | "right"} direction
     * @param {{ el: HTMLElement } | { pending: true } | null} [move]
     * @returns {HTMLElement | null}
     */
    _dispatchFutureCell(cell, cellIsInGroupRow, direction, move) {
        this._latchedMove =
            move === undefined ? null : { cell, cellIsInGroupRow, direction, move };
        try {
            return this.ctx.findFocusFutureCell(cell, cellIsInGroupRow, direction);
        } finally {
            this._latchedMove = null;
        }
    }

    resolvePendingVirtFocus() {
        const pending = this._pendingVirtFocus;
        if (!pending) {
            return;
        }
        let { rowIndex, colIndex } = pending;
        let recordStillExists = true;
        if (pending.recordId !== undefined) {
            const flat = this.ctx.getGridState?.()?.findRowByRecordId(pending.recordId);
            if (flat) {
                rowIndex = flat.globalIndex;
            } else {
                recordStillExists = false;
            }
        }
        if (!recordStillExists || (pending.retries || 0) >= MAX_VIRT_FOCUS_RETRIES) {
            this._pendingVirtFocus = null;
            return;
        }
        const position = { rowIndex, colIndex };
        const element = focusableAtTarget(
            cellAtPosition(this.tableRef, position),
            position,
        );
        if (!element) {
            pending.retries = (pending.retries || 0) + 1;
            return;
        }
        const active = document.activeElement;
        if (element === active || element.contains(active)) {
            this._pendingVirtFocus = null;
            return;
        }
        if (
            active &&
            active !== document.body &&
            active.isConnected &&
            this.tableRef.el &&
            !this.tableRef.el.contains(active)
        ) {
            this._pendingVirtFocus = null;
            return;
        }
        const origin = pending.origin;
        const toFocus =
            origin && this.ctx.findFocusFutureCell
                ? this._dispatchFutureCell(
                      origin.cell,
                      origin.cellIsInGroupRow,
                      origin.direction,
                      { el: element },
                  )
                : element;
        if (toFocus) {
            this.focus(toFocus);
        }
        pending.retries = (pending.retries || 0) + 1;
    }

    clearPendingVirtFocus() {
        this._pendingVirtFocus = null;
    }

    /**
     * @param {HTMLTableCellElement} cell
     * @param {boolean} cellIsInGroupRow
     * @param {"up" | "down" | "left" | "right"} direction
     */
    setPendingVirtFocusOrigin(cell, cellIsInGroupRow, direction) {
        if (this._pendingVirtFocus) {
            this._pendingVirtFocus.origin = { cell, cellIsInGroupRow, direction };
        }
    }

    /**
     * @param {HTMLTableCellElement} cell
     * @param {boolean} cellIsInGroupRow
     * @param {"up" | "down" | "left" | "right"} direction
     * @returns {{ el: HTMLElement } | { pending: true } | null}
     */
    findFocusMove(cell, cellIsInGroupRow, direction) {
        const gridState = this.ctx.getGridState?.();
        const row = cell.parentElement;
        if (gridState && row.dataset.rowIndex !== undefined) {
            const move = this._findGridFocusMove(gridState, cell, row, direction);
            if (move) {
                return move;
            }
        }
        const children = /** @type {HTMLElement[]} */ ([...row.children]);
        const index = children.indexOf(/** @type {HTMLElement} */ (cell));
        let futureCell;
        if (gridState?.isRTL && (direction === "left" || direction === "right")) {
            direction = direction === "left" ? "right" : "left";
        }
        let el = null;
        if (direction === "up" || direction === "down") {
            const vertical = verticalNeighbourCell(row, index, {
                direction,
                cellIsInGroupRow,
                lastKnownIndex: this._lastKnownIndex,
                isHeaderRow: this.tableRef.el.querySelector("thead tr") === row,
            });
            if (vertical) {
                futureCell = vertical.cell;
                this._lastKnownIndex = vertical.lastKnownIndex;
                if (vertical.rememberColumn !== undefined) {
                    this.ctx.getGridState?.()?.rememberColumn(vertical.rememberColumn);
                }
            }
            el = futureCell ? focusableInColumnFrom(futureCell, direction) : null;
        } else {
            const step = direction === "left" ? -1 : 1;
            for (let i = index + step; i >= 0 && i < children.length; i += step) {
                el = getFocusableInCell(children[i]);
                if (el) {
                    this._lastKnownIndex = i;
                    const skipped = Math.abs(i - index) - 1;
                    if (skipped) {
                        log.logic("arrow.skipCells", () => ({
                            path: "dom",
                            direction,
                            from: index,
                            to: i,
                            skipped,
                        }));
                    }
                    break;
                }
            }
        }
        return el ? { el } : null;
    }

    /**
     * @param {import("./list_grid_state").ListGridState} gridState
     * @param {HTMLTableCellElement} cell
     * @param {HTMLElement} row
     * @param {"up" | "down" | "left" | "right"} direction
     * @returns {{ el: HTMLElement } | { pending: true } | null}
     */
    _findGridFocusMove(gridState, cell, row, direction) {
        const rowIndex = Number.parseInt(row.dataset.rowIndex, 10);
        const colIndex =
            cell.dataset.colIndex !== undefined
                ? Number.parseInt(cell.dataset.colIndex, 10)
                : [...row.children].indexOf(cell);
        const isHorizontal = direction === "left" || direction === "right";
        const next = gridState.moveFocus(
            rowIndex,
            colIndex,
            direction,
            (nextRowIndex, nextColIndex) =>
                this._canTakeFocusAt(nextRowIndex, nextColIndex, colIndex, direction),
        );
        if (!next) {
            return null;
        }
        const target = cellAtPosition(
            this.tableRef,
            next,
            isHorizontal ? (next.colIndex > colIndex ? "right" : "left") : undefined,
        );
        const rendered = target.rendered;
        const element = focusableAtTarget(target, next);
        if (gridState.rowAt(next.rowIndex)?.type !== "group") {
            this._lastKnownIndex = next.colIndex;
        }
        if (element) {
            return { el: element };
        }
        if (rendered) {
            return null;
        }
        const virt = this.ctx.getVirtualization?.();
        if (!virt?.isActive) {
            return null;
        }
        virt.scrollRowIntoView(next.rowIndex);
        const flat = gridState.flatRows[next.rowIndex];
        this._pendingVirtFocus = {
            rowIndex: next.rowIndex,
            colIndex: next.colIndex,
            recordId:
                flat?.type === "record" && flat.record
                    ? String(flat.record.id)
                    : undefined,
        };
        return { pending: true };
    }

    /**
     * @param {number} rowIndex
     * @param {number} colIndex
     * @param {number} fromColIndex
     * @param {"up" | "down" | "left" | "right"} direction
     * @returns {boolean}
     */
    _canTakeFocusAt(rowIndex, colIndex, fromColIndex, direction) {
        const target = cellAtPosition(
            this.tableRef,
            { rowIndex, colIndex },
            colIndex > fromColIndex ? "right" : "left",
        );
        if (!target.rendered || !target.cell || target.addLine) {
            return true;
        }
        const canTakeFocus = Boolean(getFocusableInCell(target.cell));
        if (!canTakeFocus) {
            log.logic("arrow.skipCells", () => ({
                path: "grid",
                direction,
                rowIndex,
                from: fromColIndex,
                skippedCol: colIndex,
            }));
        }
        return canTakeFocus;
    }

    /**
     * @param {HTMLTableCellElement} cell
     * @param {boolean} cellIsInGroupRow
     * @param {"up" | "down" | "left" | "right"} direction
     * @returns {HTMLElement | null}
     */
    findFocusFutureCell(cell, cellIsInGroupRow, direction) {
        const latched = this._latchedMove;
        const move =
            latched &&
            latched.cell === cell &&
            latched.cellIsInGroupRow === cellIsInGroupRow &&
            latched.direction === direction
                ? latched.move
                : this.findFocusMove(cell, cellIsInGroupRow, direction);
        return move && "el" in move ? move.el : null;
    }

    /**
     * @param {HTMLElement} row
     * @param {HTMLTableCellElement} [cell]
     * @returns {HTMLElement | null}
     */
    findNextFocusableOnRow(row, cell) {
        return findNextFocusableOnRow(row, cell);
    }

    /**
     * @param {HTMLElement} row
     * @param {HTMLTableCellElement} [cell]
     * @returns {HTMLElement | null}
     */
    findPreviousFocusableOnRow(row, cell) {
        return findPreviousFocusableOnRow(row, cell);
    }

    /**
     * @param {string} hotkey
     * @param {HTMLTableCellElement} cell
     * @returns {boolean}
     */
    toggleFocusInsideCell(hotkey, cell) {
        return togglesFocusInsideCell(hotkey, cell);
    }

    /**
     * @param {HTMLTableCellElement} cell
     * @param {boolean} cellIsInGroupRow
     * @param {"up"|"down"|"left"|"right"} direction
     * @returns {HTMLElement | true | null}
     */
    resolveArrowMove(cell, cellIsInGroupRow, direction) {
        const move = this.findFocusMove(cell, cellIsInGroupRow, direction);
        if (move && "pending" in move) {
            this.setPendingVirtFocusOrigin(cell, cellIsInGroupRow, direction);
            return true;
        }
        if (this.ctx.findFocusFutureCell) {
            return this._dispatchFutureCell(cell, cellIsInGroupRow, direction, move);
        }
        return move && "el" in move ? move.el : null;
    }

    /**
     * @param {"up" | "down" | "left" | "right"} direction
     * @param {HTMLTableCellElement} cell
     * @param {boolean} cellIsInGroupRow
     * @param {import("./list_renderer").Group | null} group
     * @returns {{ handled: true } | { toFocus: Element | null }}
     */
    _readOnlyArrow(direction, cell, cellIsInGroupRow, group) {
        if (cellIsInGroupRow && direction === "left" && !group.isFolded) {
            this.ctx.onToggleGroup(group);
            return { handled: true };
        }
        if (cellIsInGroupRow && direction === "right" && group.isFolded) {
            this.ctx.onToggleGroup(group);
            return { handled: true };
        }
        if (
            (direction === "left" || direction === "right") &&
            cell.classList.contains("o_field_x2many_list_row_add")
        ) {
            const a = document.activeElement;
            return {
                toFocus:
                    direction === "left"
                        ? a.previousElementSibling
                        : a.nextElementSibling,
            };
        }
        const moved = this.resolveArrowMove(cell, cellIsInGroupRow, direction);
        if (moved === true) {
            return { handled: true };
        }
        const searchModel = this.ctx.getSearchModel();
        if (!moved && direction === "up" && searchModel) {
            log.logic("arrow.topEdgeToSearch", () => ({
                row: cell.parentElement.closest("thead") ? "header" : "body",
                cellIndex: [...cell.parentElement.children].indexOf(cell),
                cellIsInGroupRow,
            }));
            searchModel.trigger(SearchModelEvent.FOCUS_SEARCH);
            return { handled: true };
        }
        return { toFocus: moved };
    }

    /**
     * @param {HTMLTableCellElement} cell
     * @param {boolean} cellIsInGroupRow
     * @param {import("./list_renderer").Group | null} group
     * @param {import("./list_renderer").RelationalRecord | null} record
     * @param {boolean} applyMultiEditBehavior
     * @returns {boolean}
     */
    _readOnlyEnter(cell, cellIsInGroupRow, group, record, applyMultiEditBehavior) {
        if (!group && !record) {
            return false;
        }
        if (cell.classList.contains("o_list_record_remove")) {
            this.ctx.onDeleteRecord(record);
            return true;
        }
        if (cellIsInGroupRow) {
            const button = document.activeElement.closest("button");
            if (button) {
                button.click();
            } else {
                this.ctx.onToggleGroup(group);
            }
            return true;
        }
        if (this.ctx.isInlineEditable(record) || applyMultiEditBehavior) {
            const column = this.ctx
                .getColumns()
                .find((c) => c.name === cell.getAttribute("name"));
            this.cellToFocus = { column, record };
            this.ctx.getProps().list.enterEditMode(record);
            return true;
        }
        if (!this.ctx.getProps().archInfo.noOpen) {
            this.ctx.onOpenRecord(record);
            return true;
        }
        return false;
    }

    /**
     * @param {string} hotkey
     * @param {HTMLTableCellElement} cell
     * @param {import("./list_renderer").Group | null} group
     * @param {import("./list_renderer").RelationalRecord | null} record
     * @returns {boolean}
     */
    onCellKeydownReadOnlyMode(hotkey, cell, group, record) {
        const cellIsInGroupRow = Boolean(group && !record);
        const applyMultiEditBehavior =
            record?.selected && this.ctx.getProps().list.model.multiEdit;
        let toFocus;
        switch (hotkey) {
            case "arrowup":
            case "arrowdown":
            case "arrowleft":
            case "arrowright": {
                const direction = /** @type {"up" | "down" | "left" | "right"} */ (
                    hotkey.slice(5)
                );
                const arrow = this._readOnlyArrow(
                    direction,
                    cell,
                    cellIsInGroupRow,
                    group,
                );
                if ("handled" in arrow) {
                    return true;
                }
                toFocus = arrow.toFocus;
                break;
            }
            case "tab":
            case "shift+tab":
                if (cellIsInGroupRow) {
                    toFocus = adjacentGroupButton(cell, hotkey === "tab" ? 1 : -1);
                }
                break;
            case "shift+arrowdown":
            case "shift+arrowup": {
                const direction = hotkey === "shift+arrowdown" ? "down" : "up";
                if (this.ctx.expandCheckboxes(record, direction)) {
                    const moved = this.resolveArrowMove(
                        cell,
                        cellIsInGroupRow,
                        direction,
                    );
                    if (moved === true) {
                        return true;
                    }
                    toFocus = moved;
                }
                break;
            }
            case "shift+space":
                if (!record) {
                    return false;
                }
                this.ctx.toggleRecordSelection(record);
                toFocus = getElementToFocus(cell);
                break;
            case "shift":
                this.ctx.getSel().shiftKeyedRecord = record;
                break;
            case "enter":
                return this._readOnlyEnter(
                    cell,
                    cellIsInGroupRow,
                    group,
                    record,
                    applyMultiEditBehavior,
                );
            default:
                return false;
        }
        if (toFocus) {
            this.focus(/** @type {HTMLElement} */ (toFocus));
            return true;
        }
        return false;
    }
}

/**
 * @param {any} tableRef
 * @param {ListKeyboardContext} ctx
 * @returns {ListKeyboardNavigation & import("./list_keyboard_edit").ListEditHandlers}
 */
export function useListKeyboardNavigation(tableRef, ctx) {
    const nav = /** @type {any} */ (new ListKeyboardNavigation(tableRef, ctx));
    Object.assign(nav, makeEditHandlers(nav, tableRef, ctx));

    useFieldDirtyOwners(ctx.getProps().list.model, (fieldIsDirty) => {
        nav.lastIsDirty = fieldIsDirty;
    });

    const searchModel = ctx.getSearchModel();
    if (searchModel) {
        useBus(searchModel, SearchModelEvent.FOCUS_VIEW, () => {
            if (ctx.getProps().list.model.useSampleModel) {
                return;
            }
            const nextTh = tableRef.el?.querySelector("thead th");
            if (!nextTh) {
                return;
            }
            const toFocus = /** @type {HTMLElement} */ (
                getTabableElements(nextTh).at(0) || nextTh
            );
            nav.focus(toFocus);
            ctx.setKeyboardNavigation(true);
        });
    }

    return nav;
}
