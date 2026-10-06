// @ts-check

import { afterEach } from "@odoo/hoot";
import { _drainColorSchemeListeners } from "@web/core/color_scheme";
import { makeLogger } from "@web/core/debug/debug_logger";

const log = makeLogger("web.tests.color_scheme");

/** @param {Function} listener */
function describeListener(listener) {
    return listener.name || String(listener).replace(/\s+/g, " ").slice(0, 80);
}

/** @returns {string[]} */
export function takeColorSchemeLeaks() {
    const leaked = _drainColorSchemeListeners().map(describeListener);
    log.logic("check", () => ({ leaked: leaked.join(" | ") }));
    return leaked;
}

export function checkColorSchemeListeners() {
    afterEach(() => {
        const leaked = takeColorSchemeLeaks();
        if (leaked.length) {
            throw new Error(
                `${leaked.length} colour scheme listener(s) outlived the test ` +
                    `(whoever subscribed never unsubscribed): ${leaked.join(" | ")}`,
            );
        }
    });
}
