// @ts-check
/** @odoo-module native */

import { markup } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { morph, toFragment } from "@web/core/utils/dom/morph";

/** @typedef {import("@web/public/interaction_service").InteractionService} InteractionService */

/**
 * The payload of web/controllers/utils.py render_fragments.
 *
 * @typedef {Object} FragmentResponse
 * @property {{ key: string, html: string, swap: "morph" | "inner" | "outer" }[]} fragments
 * @property {{ name: string, detail: Record<string, any> }[]} events
 * @property {string | null} redirect
 * @property {Record<string, any>} data
 */

/**
 * Swaps each fragment into every element of the page carrying its
 * `data-fragment` key, restarting the interactions inside it and refreshing
 * those around it, then dispatching a bubbling `o-fragment-swapped` on it
 * (htmx's `htmx:afterSwap`) for the interactions around it whose own work
 * covers the elements it holds; then dispatches the events on `document` and
 * follows the redirect. A key with no element on this page is skipped: the page does not
 * show that region.
 *
 * @param {FragmentResponse} response
 * @param {{ interactions: InteractionService, root?: ParentNode }} options
 * @returns {Record<string, any>} the response's `data`
 */
export function applyFragments(response, { interactions, root = document }) {
    for (const { key, html, swap } of response.fragments) {
        const targets = /** @type {NodeListOf<HTMLElement>} */ (
            root.querySelectorAll(`[data-fragment="${CSS.escape(key)}"]`)
        );
        for (const target of targets) {
            if (!target.isConnected) {
                continue;
            }
            interactions.stopInteractions(target);
            const swapped = swapInto(target, markup(html), swap);
            interactions.startInteractions(swapped);
            interactions.updateEnclosing(swapped);
            swapped.dispatchEvent(
                new CustomEvent("o-fragment-swapped", { bubbles: true }),
            );
        }
    }
    for (const { name, detail } of response.events) {
        document.dispatchEvent(new CustomEvent(name, { detail }));
    }
    if (response.redirect) {
        browser.location.assign(response.redirect);
    }
    return response.data;
}

/**
 * @param {HTMLElement} target
 * @param {import("@odoo/owl").Markup} html
 * @param {"morph" | "inner" | "outer"} swap
 * @returns {HTMLElement} the element now standing where `target` stood
 */
function swapInto(target, html, swap) {
    const newRoot = /** @type {HTMLElement} */ (toFragment(html).firstElementChild);
    if (swap === "outer") {
        target.replaceWith(newRoot);
        return newRoot;
    }
    if (swap === "inner") {
        const children = document.createDocumentFragment();
        children.append(...newRoot.childNodes);
        morph(target, children, { inner: true });
        return target;
    }
    const parent = target.parentElement;
    const next = target.nextSibling;
    morph(target, newRoot);
    if (target.isConnected) {
        return target;
    }
    let node = next ? next.previousSibling : parent.lastChild;
    while (node && !(node instanceof HTMLElement)) {
        node = node.previousSibling;
    }
    return /** @type {HTMLElement} */ (node);
}
