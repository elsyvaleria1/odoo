// @ts-check
/** @odoo-module native */

import { getDefault } from "@odoo/owl";

/**
 * @template {Record<string, any>} P
 * @param {P} props
 * @param {Record<string, any> | undefined} defaults
 * @returns {P}
 */
export function withDefaults(props, defaults) {
    if (!defaults) {
        return props;
    }
    return new Proxy(props, {
        get(target, key, receiver) {
            const value = Reflect.get(target, key, receiver);
            return value === undefined && key in defaults
                ? defaults[/** @type {string} */ (key)]
                : value;
        },
        has(target, key) {
            return key in target || key in defaults;
        },
        ownKeys(target) {
            return [...new Set([...Reflect.ownKeys(target), ...Object.keys(defaults)])];
        },
        getOwnPropertyDescriptor(target, key) {
            const descriptor = Reflect.getOwnPropertyDescriptor(target, key);
            if (
                descriptor &&
                (descriptor.get
                    ? descriptor.get() !== undefined
                    : descriptor.value !== undefined)
            ) {
                return descriptor;
            }
            if (typeof key === "string" && key in defaults) {
                return {
                    value: defaults[key],
                    enumerable: true,
                    configurable: true,
                    writable: false,
                };
            }
            return descriptor;
        },
    });
}

/**
 * @param {Record<string, any>} schema
 * @returns {Record<string, any>}
 */
export function propDefaults(schema) {
    /** @type {Record<string, any>} */
    const defaults = {};
    for (const [key, type] of Object.entries(schema)) {
        const factory = getDefault(type);
        if (factory) {
            defaults[key] = factory();
        }
    }
    return defaults;
}
