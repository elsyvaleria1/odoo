// @ts-check
/** @odoo-module native */

import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { makeLogger } from "@web/core/debug/debug_logger";
import { getTabableElements, isFocusable } from "@web/core/utils/dom/ui";

const log = makeLogger("web.view.list");

const CONTROL_SELECTOR = "[tabindex], a[href], button, input, select, textarea";
const TEXT_INPUT_TYPES = [
    "text",
    "search",
    "url",
    "tel",
    "password",
    "email",
    "number",
];
const ARROW_DIRECTIONS = /** @type {const} */ ({
    arrowup: "up",
    arrowdown: "down",
    arrowleft: "left",
    arrowright: "right",
});

/**
 * @param {HTMLTableCellElement} cell
 * @param {number} [index]
 * @returns {HTMLElement}
 */
export function getElementToFocus(cell, index) {
    return /** @type {HTMLElement} */ (getTabableElements(cell).at(index ?? 0) || cell);
}

/**
 * @param {Element} cell
 * @returns {HTMLElement | null}
 */
export function getFocusableInCell(cell) {
    const tabable = getTabableElements(/** @type {HTMLElement} */ (cell)).at(0);
    if (tabable) {
        return tabable;
    }
    if (cell.hasAttribute("tabindex")) {
        return /** @type {HTMLElement} */ (cell);
    }
    const control =
        /** @type {HTMLElement[]} */ ([
            ...cell.querySelectorAll(CONTROL_SELECTOR),
        ]).find((el) => isFocusable(el)) ?? null;
    if (control) {
        log.logic("focusable.untabbableControl", () => ({
            cell: cell.className,
            control: control.className,
        }));
    }
    return control;
}

/**
 * @param {Element} el
 * @param {"up" | "down" | "left" | "right"} direction
 * @returns {boolean}
 */
function caretCanMove(el, direction) {
    if (/** @type {HTMLElement} */ (el).isContentEditable) {
        return true;
    }
    const isTextArea = el.tagName === "TEXTAREA";
    if (
        !isTextArea &&
        !(
            el.tagName === "INPUT" &&
            TEXT_INPUT_TYPES.includes(/** @type {HTMLInputElement} */ (el).type)
        )
    ) {
        return false;
    }
    const input = /** @type {HTMLInputElement | HTMLTextAreaElement} */ (el);
    const { selectionStart, selectionEnd, value } = input;
    if (selectionStart === null || selectionEnd === null) {
        return false;
    }
    if (selectionStart !== selectionEnd) {
        return true;
    }
    return direction === "left" || direction === "up"
        ? selectionStart > 0
        : selectionEnd < value.length;
}

/**
 * @param {KeyboardEvent} ev
 * @returns {"up" | "down" | "left" | "right" | null}
 */
export function arrowLeavingTarget(ev) {
    const direction =
        ARROW_DIRECTIONS[
            /** @type {keyof typeof ARROW_DIRECTIONS} */ (getActiveHotkey(ev))
        ];
    if (!direction) {
        return null;
    }
    const keepsCaret = caretCanMove(/** @type {Element} */ (ev.target), direction);
    log.logic("arrow.leavesTarget", () => ({
        direction,
        target: /** @type {Element} */ (ev.target).tagName,
        keepsCaret,
    }));
    return keepsCaret ? null : direction;
}

/**
 * @param {HTMLElement} parent
 * @returns {boolean}
 */
export function containsActiveElement(parent) {
    const { activeElement } = document;
    return parent !== activeElement && parent.contains(activeElement);
}

/**
 * @param {string} hotkey
 * @param {HTMLTableCellElement} cell
 * @returns {boolean}
 */
export function togglesFocusInsideCell(hotkey, cell) {
    if (!["tab", "shift+tab"].includes(hotkey) || !containsActiveElement(cell)) {
        return false;
    }
    const focusableEls = getTabableElements(cell).filter(
        (el) =>
            el === document.activeElement ||
            ["INPUT", "BUTTON", "TEXTAREA"].includes(el.tagName),
    );
    const index = focusableEls.indexOf(
        /** @type {HTMLElement} */ (document.activeElement),
    );
    if (index === -1) {
        return false;
    }
    return hotkey === "tab" ? index < focusableEls.length - 1 : index > 0;
}

/**
 * @param {HTMLElement} candidate
 * @returns {boolean}
 */
function canTakeFocus(candidate) {
    if (!candidate.classList.contains("o_data_cell")) {
        return false;
    }
    return !candidate.firstElementChild?.classList.contains("o_readonly_modifier");
}

/**
 * @param {HTMLElement} row
 * @param {HTMLElement} [cell]
 * @returns {HTMLElement | null}
 */
export function findNextFocusableOnRow(row, cell) {
    const children = /** @type {HTMLElement[]} */ ([...row.children]);
    const index = children.indexOf(/** @type {HTMLElement} */ (cell));
    for (const candidate of children.slice(index + 1)) {
        if (!canTakeFocus(candidate)) {
            continue;
        }
        const toFocus = getElementToFocus(
            /** @type {HTMLTableCellElement} */ (candidate),
            0,
        );
        if (toFocus !== candidate) {
            return toFocus;
        }
    }
    return null;
}

/**
 * @param {HTMLElement} row
 * @param {HTMLElement} [cell]
 * @returns {HTMLElement | null}
 */
export function findPreviousFocusableOnRow(row, cell) {
    const children = /** @type {HTMLElement[]} */ ([...row.children]);
    const index = cell ? children.indexOf(cell) : children.length;
    for (const candidate of children.slice(0, index).reverse()) {
        if (!canTakeFocus(candidate)) {
            continue;
        }
        const toFocus = getElementToFocus(
            /** @type {HTMLTableCellElement} */ (candidate),
            -1,
        );
        if (toFocus !== candidate) {
            return toFocus;
        }
    }
    return null;
}

/**
 * @param {HTMLElement | null | undefined} el
 * @returns {void}
 */
export function focusAndSelect(el) {
    if (!el) {
        return;
    }
    el.focus();
    const inputEl = /** @type {HTMLInputElement} */ (el);
    if (
        ["text", "search", "url", "tel", "password", "textarea"].includes(
            inputEl.type,
        ) &&
        inputEl.selectionStart === inputEl.selectionEnd
    ) {
        inputEl.selectionStart = 0;
        inputEl.selectionEnd = inputEl.value.length;
    }
}
