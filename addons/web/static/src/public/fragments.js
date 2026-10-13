// @ts-check
/** @odoo-module native */

import { browser } from "@web/core/browser/browser";
import { morph } from "@web/core/utils/dom/morph";

/** @typedef {import("@web/public/interaction_service").InteractionService} InteractionService */

/**
 * @typedef {Object} FragmentResponse
 * @property {{ key: string, html: string, swap: "morph" | "inner" | "outer" }[]} fragments
 * @property {{ name: string, detail: Record<string, any> }[]} events
 * @property {string | null} redirect
 * @property {Record<string, any>} data
 */

/**
 * @param {FragmentResponse} response
 * @param {{ interactions: InteractionService, root?: ParentNode }} options
 * @returns {Record<string, any>}
 */
export function applyFragments(response, { interactions, root = document }) {
    for (const { key, html, swap } of response.fragments) {
        const targets = /** @type {NodeListOf<HTMLElement>} */ (
            root.querySelectorAll(`[data-fragment="${CSS.escape(key)}"]`)
        );
        for (const target of targets) {
            if (target.isConnected) {
                swapFragment(target, html, swap, interactions);
            }
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
 * @param {string} html
 * @param {"morph" | "inner" | "outer"} swap
 * @param {InteractionService} interactions
 * @returns {HTMLElement}
 */
export function swapFragment(target, html, swap, interactions) {
    interactions.stopInteractions(target);
    const swapped = swapInto(target, html, swap);
    interactions.startInteractions(swapped);
    interactions.updateEnclosing(swapped);
    swapped.dispatchEvent(new CustomEvent("o-fragment-swapped", { bubbles: true }));
    return swapped;
}

/**
 * @param {HTMLElement} target
 * @param {string} html
 * @param {"morph" | "inner" | "outer"} swap
 * @returns {HTMLElement}
 */
function swapInto(target, html, swap) {
    const template = document.createElement("template");
    template.innerHTML = html;
    const newRoot = /** @type {HTMLElement} */ (template.content.firstElementChild);
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
