// @ts-check
/** @odoo-module native */

import { untrack, useScope } from "@odoo/owl";

/** @returns {any} */
function currentNode() {
    return useScope();
}

/**
 * Runs `callback` before each render of the calling component, as OWL 2's
 * onWillRender did. What it reads subscribes the render, as reads through a
 * component's useState proxy did.
 *
 * @param {() => void} callback
 */
export function onWillRender(callback) {
    const node = currentNode();
    const render = node.renderFn;
    node.renderFn = (/** @type {any[]} */ ...args) => {
        callback.call(node.component);
        return render(...args);
    };
}

/**
 * Runs `callback` after each render of the calling component, before it is
 * patched, as OWL 2's onRendered did. What it reads does not subscribe the
 * render: those callbacks write what they read (a refresh token), which would
 * re-render forever.
 *
 * @param {() => void} callback
 */
export function onRendered(callback) {
    const node = currentNode();
    const render = node.renderFn;
    node.renderFn = (/** @type {any[]} */ ...args) => {
        const bdom = render(...args);
        untrack(() => callback.call(node.component));
        return bdom;
    };
}

/**
 * @returns {(deep?: boolean) => Promise<void>} forces a render of the calling
 * component, as OWL 2's Component#render did
 */
export function useRender() {
    const node = currentNode();
    return (deep = false) => node.render(deep === true);
}
