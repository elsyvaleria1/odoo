// @ts-check
/** @odoo-module native */

import { onMounted, onPatched, onWillDestroy, proxy, toRaw, untrack } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";

/**
 * @typedef Build
 * @property {unknown[]} source
 * @property {number} built
 * @property {number} step
 * @property {boolean} complete
 * @property {Set<unknown>} keys
 */

/**
 * @template T
 * @typedef ScreenfulFirst
 * @property {(owner: object, items: T[], whole?: boolean) => T[]} leading
 */

/**
 * @template T
 * @param {object} params
 * @param {(mounted: boolean) => number} params.screenful
 * @param {(item: T) => unknown} [params.keyOf]
 * @returns {ScreenfulFirst<T>}
 */
export function useScreenfulFirst({ screenful, keyOf = (item) => item }) {
    const round = proxy({ value: 0 });
    /** @type {WeakMap<object, Build>} */
    const builds = new WeakMap();
    /** @type {Set<Build>} */
    let rendered = new Set();
    let rendering = false;
    let mounted = false;
    /** @type {number | undefined} */
    let timer;

    /**
     * @param {Build | undefined} previous
     * @param {unknown[]} source
     * @returns {Build}
     */
    function start(previous, source) {
        const step = Math.max(
            1,
            untrack(() => screenful(mounted)),
        );
        let built = Math.min(source.length, step);
        if (previous) {
            let kept = 0;
            for (let index = source.length - 1; index >= 0; index--) {
                if (previous.keys.has(keyOf(/** @type {T} */ (source[index])))) {
                    kept = index + 1;
                    break;
                }
            }
            const reached =
                kept && !previous.complete
                    ? Math.min(source.length, previous.built)
                    : 0;
            built = Math.max(built, kept, reached);
        }
        return { source, built, step, complete: false, keys: new Set() };
    }

    function grow() {
        timer = undefined;
        let grew = false;
        for (const build of rendered) {
            if (build.built < build.source.length) {
                build.built = Math.min(build.source.length, build.built + build.step);
                grew = true;
            }
        }
        if (grew) {
            round.value++;
        }
    }

    function scheduleGrowth() {
        if (timer !== undefined) {
            return;
        }
        for (const build of rendered) {
            if (build.built < build.source.length) {
                timer = browser.setTimeout(grow);
                return;
            }
        }
    }

    onMounted(() => {
        mounted = true;
        scheduleGrowth();
    });
    onPatched(scheduleGrowth);
    onWillDestroy(() => browser.clearTimeout(timer));

    return {
        leading(owner, items, whole = false) {
            void round.value;
            if (!rendering) {
                rendering = true;
                rendered = new Set();
                queueMicrotask(() => {
                    rendering = false;
                });
            }
            const source = /** @type {unknown[]} */ (toRaw(items));
            let build = builds.get(owner);
            if (!build || build.source !== source) {
                build = start(build, source);
                builds.set(owner, build);
            }
            if (whole || build.complete) {
                build.built = source.length;
            }
            build.complete = build.built >= source.length;
            rendered.add(build);
            const leading = build.complete ? items : items.slice(0, build.built);
            build.keys = new Set(leading.map(keyOf));
            return leading;
        },
    };
}
