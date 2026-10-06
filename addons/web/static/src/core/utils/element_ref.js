// @ts-check
/** @odoo-module native */

import { signal } from "@odoo/owl";

/** @typedef {import("@odoo/owl").Signal<HTMLElement | null> & { readonly el: HTMLElement | null }} ElementRef */

/**
 * @template {HTMLElement} [T=HTMLElement]
 * @param {new (...args: any[]) => T} [type]
 */
export function elementRef(type) {
    const ref = type ? signal.ref(type) : signal.ref();
    // `.el` keeps OWL 2's ref reading; the signal call `ref()` is the native one
    Object.defineProperty(ref, "el", { get: ref });
    return /** @type {typeof ref & { readonly el: T | null }} */ (ref);
}

// the ref a template binds where it keeps no element, since t-ref cannot be conditional
export const noRef = Object.freeze({ set() {} });

/** @returns {Record<string, ElementRef>} */
export function elementRefs() {
    return new Proxy(
        /** @type {Record<string, ElementRef>} */ ({}),
        {
            get: (refs, name) =>
                typeof name === "string" ? (refs[name] ??= elementRef()) : undefined,
        },
    );
}
