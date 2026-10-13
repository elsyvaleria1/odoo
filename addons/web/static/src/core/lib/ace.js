// @ts-check
/** @odoo-module native */

import { makeLazyLib } from "@web/core/lib/lazy_lib";

const aceLib = makeLazyLib(async () => {
    const [module, qweb] = await Promise.all([import("ace"), import("ace-mode-qweb")]);
    return { ...module, modes: { ...module.modes, qweb: qweb.Mode } };
});

/** @type {any} */
export const ace = aceLib.facade;

/** @returns {Promise<any>} */
export function loadAce() {
    return aceLib.load();
}
