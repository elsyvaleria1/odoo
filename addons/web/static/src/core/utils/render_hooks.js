// @ts-check
/** @odoo-module native */

import { untrack, useScope } from "@odoo/owl";

/** @returns {any} */
function currentNode() {
    return useScope();
}

/** @param {() => void} callback */
export function onWillRender(callback) {
    const node = currentNode();
    const render = node.renderFn;
    node.renderFn = (/** @type {any[]} */ ...args) => {
        callback.call(node.component);
        return render(...args);
    };
}

/** @param {() => void} callback */
export function onRendered(callback) {
    const node = currentNode();
    const render = node.renderFn;
    node.renderFn = (/** @type {any[]} */ ...args) => {
        const bdom = render(...args);
        untrack(() => callback.call(node.component));
        return bdom;
    };
}

/** @returns {(deep?: boolean) => Promise<void>} */
export function useRender() {
    const node = currentNode();
    return (deep = false) => node.render(deep === true);
}
