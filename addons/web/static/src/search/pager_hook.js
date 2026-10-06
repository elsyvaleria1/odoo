// @ts-check
/** @odoo-module native */

import { computed } from "@odoo/owl";
import { provideViewConfig, useViewConfig } from "@web/core/view_config_hooks";

/**
 * @typedef PagerUpdateParams
 * @property {number} offset
 * @property {number} limit
 */

/**
 * @typedef PagerProps
 * @property {number} offset
 * @property {number} limit
 * @property {number} total
 * @property {(params: PagerUpdateParams, hasNavigated?: boolean) => any} onUpdate
 * @property {() => number | Promise<number>} [updateTotal]
 * @property {boolean} [isEditable]
 * @property {boolean} [withAccessKey]
 */

/**
 * The control panel's pager props: a live view of what `getProps` answers,
 * recomputed when what it reads changes, not written during a render.
 *
 * @param {() => (PagerProps | undefined)} getProps
 */
export function usePager(getProps) {
    const current = computed(() => getProps() || { total: 0 });
    const pagerProps = new Proxy(
        {},
        {
            get: (_, key) => /** @type {any} */ (current())[key],
            has: (_, key) => key in current(),
            ownKeys: () => Reflect.ownKeys(current()),
            getOwnPropertyDescriptor: (_, key) =>
                key in current()
                    ? {
                          value: /** @type {any} */ (current())[key],
                          enumerable: true,
                          configurable: true,
                      }
                    : undefined,
        },
    );
    provideViewConfig({ ...useViewConfig(), pagerProps });
}
