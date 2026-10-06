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
 * @property {(owner: object, items: T[], whole?: boolean) => T[]} leading the
 * items of `owner` to build in this render: all of them when `whole`
 */

/**
 * Builds the items a screen can show in the commit that puts a collection on
 * screen, and the rest in the frames after it: the cost of the first frame
 * follows the screen, not the page size, and the DOM still ends up holding
 * every item.
 *
 * @template T
 * @param {object} params
 * @param {(mounted: boolean) => number} params.screenful how many items fill
 * what the user can see, and so how many each commit builds
 * @param {(item: T) => unknown} [params.keyOf] what identifies an item across
 * two sets of them: an item already built is never dropped to be built again
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
            // the same items in a new array, while they were still being
            // built: the count reached carries over, or it would never grow
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
                // a commit runs in an animation frame, so a timer set from it
                // fires once that frame is painted: the next items are built
                // between two frames, never ahead of the one that shows these
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
                // a render reads its collections in one go: the first read of
                // a run starts the set of what this render shows
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
                // every item was built: the collection changing in place is an
                // edit of what is on screen, not a new set to put there
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
