// @ts-check
/** @odoo-module native */

/** @type {Map<Element, number>} */
const holds = new Map();

/**
 * Makes everything but `anchor` and its ancestors inert: the page behind an open
 * dialog, while the dialog, the popovers and the notifications that live next to
 * it in `anchor` stay usable. Holds are counted, so the dialogs of a stack share
 * one inert page, and an element already inert before the first hold is left as
 * it was.
 *
 * @param {Element} anchor
 * @returns {() => void} releases this hold; releasing it again does nothing
 */
export function inertOutside(anchor) {
    /** @type {Element[]} */
    const held = [];
    for (let node = anchor; node.parentElement; node = node.parentElement) {
        for (const sibling of node.parentElement.children) {
            if (sibling === node || !(sibling instanceof HTMLElement)) {
                continue;
            }
            const count = holds.get(sibling);
            if (count === undefined && sibling.inert) {
                continue;
            }
            holds.set(sibling, (count ?? 0) + 1);
            sibling.inert = true;
            held.push(sibling);
        }
    }
    return () => {
        for (const element of held.splice(0)) {
            const count = /** @type {number} */ (holds.get(element)) - 1;
            if (count) {
                holds.set(element, count);
            } else {
                holds.delete(element);
                /** @type {HTMLElement} */ (element).inert = false;
            }
        }
    };
}

/**
 * Where a dialog's inert page starts: the main components container holding its
 * overlay (so toasts and popovers stay usable), else the overlay container.
 *
 * @param {Element} dialogElement
 * @returns {Element}
 */
export function inertAnchorOf(dialogElement) {
    return (
        dialogElement.closest(".o-main-components-container") ??
        dialogElement.closest(".o-overlay-container") ??
        dialogElement
    );
}
