// @ts-check
/** @odoo-module native */
import {
    effect,
    onMounted,
    onPatched,
    onWillUnmount,
    untrack,
    useScope,
} from "@odoo/owl";

/**
 * @param {(...dependencies: any[]) => void | (() => void)} effectFn
 * @param {() => unknown[]} [computeDependencies]
 */
export function useLayoutEffect(effectFn, computeDependencies = () => [NaN]) {
    const node = /** @type {any} */ (useScope());
    /** @type {void | (() => void)} */
    let cleanup;
    /** @type {unknown[]} */
    let dependencies;
    /** @type {(() => void) | null} */
    let stopTracking = null;

    function trackDependencies() {
        stopTracking?.();
        /** @type {unknown[]} */
        let result = [];
        let first = true;
        stopTracking = effect(() => {
            if (first) {
                first = false;
                result = computeDependencies();
                return;
            }
            try {
                computeDependencies();
            } catch {}
            if (!node.fiber) {
                untrack(() => node.render(false));
            }
        });
        return result;
    }

    onMounted(() => {
        dependencies = trackDependencies();
        cleanup = effectFn(...dependencies);
    });
    onPatched(() => {
        const newDeps = trackDependencies();
        if (newDeps.some((value, index) => value !== dependencies[index])) {
            dependencies = newDeps;
            if (cleanup) {
                cleanup();
            }
            cleanup = effectFn(...dependencies);
        }
    });
    onWillUnmount(() => {
        stopTracking?.();
        stopTracking = null;
        if (cleanup) {
            cleanup();
        }
    });
}
