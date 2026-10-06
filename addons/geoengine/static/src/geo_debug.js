// @ts-check
/** @odoo-module native */

import { makeLogger } from "@web/core/debug/debug_logger";

/** @typedef {import("@web/core/debug/debug_logger").DebugLogger} DebugLogger */

/**
 * @param {string} prefix
 * @returns {((message: string, data?: unknown) => void) & { log: DebugLogger }}
 */
export function makeGeoLogger(prefix) {
    const log = makeLogger(`geoengine.${prefix}`);
    /** @type {any} */
    const debugLog = (/** @type {string} */ message, data = null) => {
        if (data === null) {
            log.logic(message);
        } else {
            log.logic(message, data);
        }
    };
    debugLog.log = log;
    return debugLog;
}
