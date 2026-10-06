// @ts-check
/** @odoo-module native */

import { observe, proxy } from "@odoo/owl";

export class SignalStore {
    constructor() {
        return proxy(this);
    }
}

/**
 * @template {object[]} T
 * @param {(...args: [...T]) => any} cb
 * @param {[...T]} deps
 * @returns {() => void}
 */
export function effect(cb, deps) {
    let disposed = false;
    const reactiveDeps = observe(deps, () => {
        if (disposed) {
            return;
        }
        cb(...reactiveDeps);
    });
    cb(...reactiveDeps);
    return () => {
        disposed = true;
    };
}
