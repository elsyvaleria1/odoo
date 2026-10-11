// @ts-check
/** @odoo-module native */

import { makeLazyLib } from "@web/core/lib/lazy_lib";

const aceLib = makeLazyLib(async () => {
    const [module, qweb] = await Promise.all([import("ace"), import("ace-mode-qweb")]);
    return { ...module, modes: { ...module.modes, qweb: qweb.Mode } };
});

/**
 * The Ace namespace (`edit`, `EditSession`, `UndoManager`, `Range`, the mode
 * classes under `modes` and the theme modules under `themes`), usable once
 * `loadAce()` resolved.
 *
 * @type {any}
 */
export const ace = aceLib.facade;

/**
 * Loads Ace and its modes once. Rejects when it cannot load.
 *
 * @returns {Promise<any>}
 */
export function loadAce() {
    return aceLib.load();
}
