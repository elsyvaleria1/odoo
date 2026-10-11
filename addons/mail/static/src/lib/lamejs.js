// @ts-check
/** @odoo-module native */
import { makeLazyLib } from "@web/core/lib/lazy_lib";

const lib = makeLazyLib(() => import("lamejs"), { pick: (module) => module.default });

/**
 * The MP3 encoder library, fetched on the first voice message.
 *
 * @type {any}
 */
export const lamejs = lib.facade;

export const lamejsLoader = {
    /** @returns {Promise<any>} */
    load: () => lib.load(),
};

/**
 * Loads lamejs once. Rejects when it cannot load, so the recorder reports it.
 *
 * @returns {Promise<any>}
 */
export function loadLamejs() {
    return lamejsLoader.load();
}
