// @ts-check
/** @odoo-module native */
import { makeLazyLib } from "@web/core/lib/lazy_lib";

const lib = makeLazyLib(() => import("lamejs"), { pick: (module) => module.default });

/** @type {any} */
export const lamejs = lib.facade;

export const lamejsLoader = {
    /** @returns {Promise<any>} */
    load: () => lib.load(),
};

/** @returns {Promise<any>} */
export function loadLamejs() {
    return lamejsLoader.load();
}
