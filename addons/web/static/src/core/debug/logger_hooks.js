// @ts-check
/** @odoo-module native */

import {
    onMounted,
    onPatched,
    onWillDestroy,
    onWillPatch,
    onWillUnmount,
    useProps,
    useScope,
} from "@odoo/owl";

/** @typedef {import("./debug_logger").DebugLogger} DebugLogger */

/**
 * @param {DebugLogger} log
 * @param {string} [name]
 */
export function useLifecycleLog(log, name) {
    const props = useProps();
    const componentName = useScope().componentName;
    const tag = name || componentName;
    const createdAt = performance.now();
    let patches = 0;
    /** @type {import("./debug_logger").PerfEnd} */
    let endPatch = () => 0;
    log.lifecycle(`${tag} setup`, () => props);
    onMounted(() => {
        log.lifecycle(`${tag} mounted`, () => ({
            sinceSetupMs: Number((performance.now() - createdAt).toFixed(2)),
        }));
    });
    onWillPatch(() => {
        patches++;
        log.lifecycle(`${tag} willPatch#${patches}`, () => props);
        endPatch = log.perf(`${tag} patch`, { n: patches });
    });
    onPatched(() => {
        endPatch();
        log.lifecycle(`${tag} patched#${patches}`);
    });
    onWillUnmount(() =>
        log.lifecycle(`${tag} willUnmount`, () => ({ renders: patches + 1, patches })),
    );
    onWillDestroy(() => log.lifecycle(`${tag} willDestroy`));
}
