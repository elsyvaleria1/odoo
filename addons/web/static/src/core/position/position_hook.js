// @ts-check
/** @odoo-module native */

import { EventBus, onWillDestroy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { reposition } from "@web/core/position/utils";
import { defineScope } from "@web/core/scope";
import { omit } from "@web/core/utils/collections/objects";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useThrottleForAnimation } from "@web/core/utils/timing";

const envScope = defineScope("web/core/position/position_hook");

/** @import { ComputePositionOptions, PositioningSolution } from "@web/core/position/utils" */

/**
 * @typedef {Object} UsePositionOptionsExtensionType
 * @property {(popperElement: HTMLElement, solution: PositioningSolution) => void} [onPositioned]
 * @typedef {ComputePositionOptions & UsePositionOptionsExtensionType} UsePositionOptions
 * @typedef PositioningControl
 * @property {() => void} lock
 * @property {() => void} unlock
 */

const POSITION_BUS = Symbol("position-bus");

/** @param {import("@odoo/owl").EventBus} bus */
function providePositionBus(bus) {
    envScope.provide({ [POSITION_BUS]: bus });
}

/** @returns {import("@odoo/owl").EventBus | undefined} */
export function usePositionBus() {
    return /** @type {any} */ (envScope.use())[POSITION_BUS];
}

/**
 * @param {import("@web/core/utils/element_ref").ElementRef} ref
 * @param {() => HTMLElement} getTarget
 * @param {UsePositionOptions} [options={}]
 * @returns {PositioningControl}
 */
export function usePosition(ref, getTarget, options = {}) {
    let lock = false;
    /** @type {ComputePositionOptions["position"]} */
    let lastPosition;
    let lastRequestedPosition = options.position;
    const update = () => {
        const targetEl = getTarget();
        if (!ref.el || !targetEl?.isConnected || lock) {
            return false;
        }
        if (options.position !== lastRequestedPosition) {
            lastRequestedPosition = options.position;
            lastPosition = undefined;
        }
        const repositionOptions = omit(options, "onPositioned");
        if (lastPosition) {
            repositionOptions.position = lastPosition;
        }
        const solution = reposition(ref.el, targetEl, repositionOptions);
        lastPosition = /** @type {ComputePositionOptions["position"]} */ (
            `${solution.direction}-${solution.variant}`
        );
        options.onPositioned?.(ref.el, solution);
        return true;
    };

    const parentBus = usePositionBus();
    const bus = parentBus || new EventBus();

    let executingUpdate = false;
    let updateRequested = false;
    const batchedUpdate = async () => {
        if (executingUpdate) {
            updateRequested = true;
            return;
        }
        executingUpdate = true;
        try {
            let positioned;
            do {
                updateRequested = false;
                positioned = update();
                await Promise.resolve();
            } while (updateRequested && !positioned);
        } finally {
            executingUpdate = false;
        }
    };
    bus.addEventListener("update", batchedUpdate);
    onWillDestroy(() => bus.removeEventListener("update", batchedUpdate));

    const isTopmost = !parentBus;
    if (isTopmost) {
        providePositionBus(bus);
    }

    useLayoutEffect(() => {
        bus.trigger("update");
    });

    if (isTopmost) {
        const throttledUpdate = useThrottleForAnimation(() => bus.trigger("update"));
        const scrollListener = (/** @type {Event} */ e) => {
            if (ref.el?.contains(/** @type {Node} */ (e.target))) {
                return;
            }
            throttledUpdate();
        };
        useLayoutEffect(
            (targetDocument) => {
                if (!targetDocument) {
                    return;
                }
                /** @type {Document[]} */
                const documents = [targetDocument];
                if (
                    targetDocument.defaultView?.top &&
                    targetDocument.defaultView.top !== targetDocument.defaultView
                ) {
                    try {
                        documents.push(targetDocument.defaultView.top.document);
                    } catch {}
                }
                for (const doc of documents) {
                    doc.addEventListener("scroll", scrollListener, { capture: true });
                    doc.addEventListener("load", throttledUpdate, { capture: true });
                }
                browser.addEventListener("resize", throttledUpdate);
                return () => {
                    for (const doc of documents) {
                        doc.removeEventListener("scroll", scrollListener, {
                            capture: true,
                        });
                        doc.removeEventListener("load", throttledUpdate, {
                            capture: true,
                        });
                    }
                    browser.removeEventListener("resize", throttledUpdate);
                };
            },
            () => [getTarget()?.ownerDocument],
        );
    }

    return {
        lock: () => {
            lock = true;
        },
        unlock: () => {
            lock = false;
            bus.trigger("update");
        },
    };
}
