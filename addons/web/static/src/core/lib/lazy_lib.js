// @ts-check
/** @odoo-module native */

import { makeLazyFacade } from "@web/core/module_bridge";

/**
 * @param {() => Promise<any>} load
 * @param {Object} [options]
 * @param {(module: any) => any} [options.pick]
 * @param {(module: any) => any} [options.extra]
 * @param {boolean} [options.constructable]
 * @returns {{ facade: any, extraFacade: any, load: () => Promise<any> }}
 */
export function makeLazyLib(load, { pick, extra, constructable = false } = {}) {
    /** @type {any} */
    let value = null;
    /** @type {any} */
    let extraValue = null;
    /** @type {Promise<any> | null} */
    let loading = null;

    const facade = makeLazyFacade(() => value, { constructable });
    const extraFacade = extra ? makeLazyFacade(() => extraValue) : undefined;

    return {
        facade,
        extraFacade,
        load() {
            if (value) {
                return Promise.resolve(facade);
            }
            loading ??= load().then(
                (module) => {
                    value = pick ? pick(module) : module;
                    if (extra) {
                        extraValue = extra(module);
                    }
                    return facade;
                },
                (error) => {
                    loading = null;
                    throw error;
                },
            );
            return loading;
        },
    };
}
