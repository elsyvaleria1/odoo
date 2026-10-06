// @ts-check

import { afterEach, beforeEach, mockHistory, mockLocation } from "@odoo/hoot";
import { mockedPerformanceNow } from "@odoo/hoot-dom-helpers-time";

const READONLY_PROPERTIES = [
    "cancelAnimationFrame",
    "clearInterval",
    "clearTimeout",
    "requestAnimationFrame",
    "setInterval",
    "setTimeout",
];

export function patchBrowserLocation() {
    const { loader } = /** @type {any} */ (window).odoo;
    const browserModule = loader.modules.get("@web/core/browser/browser");
    if (!browserModule?.browser) {
        return;
    }
    Object.defineProperty(browserModule.browser, "location", {
        get: () => mockLocation,
        set: (value) => {
            mockLocation.href = value;
        },
        configurable: true,
    });
    Object.defineProperty(browserModule.browser, "history", {
        get: () => mockHistory,
        configurable: true,
    });
    for (const property of READONLY_PROPERTIES) {
        const originalValue = browserModule.browser[property];
        Object.defineProperty(browserModule.browser, property, {
            configurable: true,
            get: () => originalValue,
        });
    }
    // A real window.open puts the test page in the background, and Chrome
    // throttles a background page's timers to one wake-up per second for the
    // rest of the run: every test after the popup then pays seconds per
    // awaited timer. A test that asserts on the call patches open itself.
    browserModule.browser.open = () => ({
        closed: false,
        focus() {},
        close() {
            this.closed = true;
        },
    });
}

/**
 * A deadline taken from `browser.performance.now()` is waited for with
 * `browser.setTimeout`: both read HOOT's clock, or the real time a loaded
 * machine spends between two awaits moves the deadline under the test.
 */
export function patchBrowserPerformance() {
    const { loader } = /** @type {any} */ (window).odoo;
    const browserModule = loader.modules.get("@web/core/browser/browser");
    if (!browserModule?.browser) {
        return;
    }
    const { performance } = browserModule.browser;
    /** @type {Record<PropertyKey, unknown>} */
    const overrides = { now: mockedPerformanceNow };
    const mockPerformance = new Proxy(overrides, {
        get(target, property) {
            if (Object.hasOwn(target, property)) {
                return target[property];
            }
            const value = Reflect.get(performance, property, performance);
            return typeof value === "function" ? value.bind(performance) : value;
        },
        has: (target, property) => property in target || property in performance,
    });
    Object.defineProperty(browserModule.browser, "performance", {
        configurable: true,
        get: () => mockPerformance,
    });
}

export function patchBrowserStorage() {
    const snapshot = (/** @type {Storage} */ storage) => {
        /** @type {[string, string][]} */
        const entries = [];
        for (let i = 0; i < storage.length; i++) {
            const key = /** @type {string} */ (storage.key(i));
            entries.push([key, /** @type {string} */ (storage.getItem(key))]);
        }
        return entries;
    };
    const restore = (
        /** @type {Storage} */ storage,
        /** @type {[string, string][]} */ entries,
    ) => {
        storage.clear();
        for (const [key, value] of entries) {
            storage.setItem(key, value);
        }
    };

    /** @type {[Storage, [string, string][]][]} */
    let taken = [];
    beforeEach(
        () => {
            const stores = [globalThis.localStorage, globalThis.sessionStorage];
            taken = stores.filter(Boolean).map((s) => [s, snapshot(s)]);
        },
        { global: true },
    );
    afterEach(
        () => {
            for (const [storage, entries] of taken) {
                restore(storage, entries);
            }
            taken = [];
        },
        { global: true },
    );
}
