// @ts-check

import { afterEach, beforeEach } from "@odoo/hoot";
import { makeLogger } from "@web/core/debug/debug_logger";
import { ServiceContainer } from "@web/core/service_container";

/** @typedef {{ name: string, mode: "sync" | "async", error: unknown }} ServiceStartFailure */

const log = makeLogger("web.tests.services");

/** @type {ServiceStartFailure[]} */
let failures = [];
/** @type {Set<string>} */
let allowed = new Set();

/** @param {...string} names */
export function allowServiceStartFailure(...names) {
    for (const name of names) {
        allowed.add(name);
    }
}

/** @returns {ServiceStartFailure[]} */
export function takeUnexpectedServiceStartFailures() {
    const unexpected = failures.filter(({ name }) => !allowed.has(name));
    log.logic("check", () => ({
        failed: failures.map(({ name, mode }) => `${name} (${mode})`).join(","),
        allowed: [...allowed].join(","),
        unexpected: unexpected.map(({ name }) => name).join(","),
    }));
    failures = [];
    allowed = new Set();
    return unexpected;
}

export function checkServiceStartFailures() {
    const { _reportFailure } = ServiceContainer.prototype;
    /**
     * @this {ServiceContainer}
     * @param {string} name
     * @param {"sync" | "async"} mode
     * @param {unknown} error
     */
    ServiceContainer.prototype._reportFailure = function (name, mode, error) {
        if (!this._destroyed) {
            failures.push({ name, mode, error });
        }
        return _reportFailure.call(this, name, mode, error);
    };
    beforeEach(() => {
        failures = [];
        allowed = new Set();
    });
    afterEach(() => {
        const unexpected = takeUnexpectedServiceStartFailures();
        if (unexpected.length) {
            const names = unexpected.map(({ name, mode }) => `"${name}" (${mode})`);
            throw new Error(
                `service ${names.join(", ")} failed to start; a test that means it ` +
                    `calls allowServiceStartFailure(name)`,
                { cause: unexpected[0].error },
            );
        }
    });
}
