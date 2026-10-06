// @ts-check
/** @odoo-module native */

import { onMounted, onWillUnmount, proxy } from "@odoo/owl";
import { cookie } from "@web/core/browser/cookie";

const COOKIE = "color_scheme";

const revision = proxy({ count: 0 });

/** @type {Set<(scheme: "light" | "dark") => void>} */
const listeners = new Set();

/** @param {typeof revision} tracked */
function subscribe(tracked) {
    return tracked.count;
}

export const colorScheme = {
    /** @returns {"light" | "dark"} */
    get current() {
        return cookie.get(COOKIE) === "dark" ? "dark" : "light";
    },
    /** @returns {boolean} */
    get isDark() {
        return this.current === "dark";
    },
    /** @param {"light" | "dark"} scheme */
    publish(scheme) {
        const changed = scheme !== this.current;
        cookie.set(COOKIE, scheme);
        document.documentElement.dataset.colorScheme = scheme;
        revision.count++;
        if (changed) {
            for (const listener of [...listeners]) {
                listener(scheme);
            }
        }
    },
    /**
     * @param {(scheme: "light" | "dark") => void} listener
     * @returns {() => void}
     */
    subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
    },
};

/** @returns {((scheme: "light" | "dark") => void)[]} */
export function _drainColorSchemeListeners() {
    const drained = [...listeners];
    listeners.clear();
    return drained;
}

/** @returns {{current: "light" | "dark", isDark: boolean}} */
export function useColorScheme() {
    const tracked = proxy(revision);
    return {
        get current() {
            subscribe(tracked);
            return colorScheme.current;
        },
        get isDark() {
            return this.current === "dark";
        },
    };
}

/** @param {(scheme: "light" | "dark") => void} effect */
export function useColorSchemeEffect(effect) {
    /** @type {(() => void) | undefined} */
    let unsubscribe;
    onMounted(() => {
        unsubscribe = colorScheme.subscribe(effect);
    });
    onWillUnmount(() => unsubscribe?.());
}
