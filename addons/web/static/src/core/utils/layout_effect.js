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

    // OWL 2 subscribed the component to whatever the dependencies read through
    // its proxies, wherever they were read: a change re-rendered it, and the
    // patch re-evaluated them. OWL 3 only tracks reads in a render or an
    // effect, so the dependencies are computed in one, and a change of what
    // they read renders the component as OWL 2 did. A render already in
    // flight is enough: onPatched re-reads the dependencies after its patch.
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
            // a change re-reads the dependencies only to keep tracking them:
            // the patch recomputes them, and meanwhile they may read a DOM
            // being replaced (a connector whose pill is gone), so a failure
            // here only means "render"
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
