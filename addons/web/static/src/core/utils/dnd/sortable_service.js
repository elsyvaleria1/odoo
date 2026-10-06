// @ts-check
/** @odoo-module native */

import { proxy } from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { registry } from "@web/core/registry";
import { useSortable } from "@web/core/utils/dnd/sortable";
import { throttleForAnimation } from "@web/core/utils/timing";

/**
 * @typedef {Record<string, any> & {
 * ref?: {el: HTMLElement} | import("@web/core/utils/hooks").Ref;
 * sortableId?: string | symbol;
 * }} SortableServiceHookParams
 */

const DEFAULT_SORTABLE_ID = Symbol.for("defaultSortable");
const log = makeLogger("web.dnd.sortable_service");

class SortableService {
    constructor() {
        /** @type {WeakMap<Element, Record<string | symbol, () => void>>} */
        this.boundElements = new WeakMap();
    }

    /** @param {{ ref: { el: Element | null }, [key: string]: any }} hookParams */
    create(hookParams) {
        if (!hookParams?.ref) {
            throw new Error(
                "sortable service: create() requires a `ref` in hookParams",
            );
        }
        const element = hookParams.ref.el;
        if (!element) {
            throw new Error(
                "sortable service: create() requires a mounted ref " +
                    "(hookParams.ref.el is not set)",
            );
        }
        const sortableId = hookParams.sortableId ?? DEFAULT_SORTABLE_ID;
        if (this.boundElements.has(element)) {
            const boundElement = this.boundElements.get(element);
            if (boundElement && sortableId in boundElement) {
                return {
                    enable() {
                        return {
                            cleanup: boundElement[sortableId] ?? (() => {}),
                        };
                    },
                };
            }
        }
        /** @type {Map<Function, () => any[]>} */
        const setupFunctions = new Map();
        /** @type {Array<Function>} */
        const hookTeardowns = [];
        /** @type {Array<Function>} */
        const enabledTeardowns = [];
        let enabled = false;

        const boundTo = () => this.boundElements.get(element)?.[sortableId];

        const bind = () => {
            const boundElement = this.boundElements.get(element);
            if (boundElement) {
                boundElement[sortableId] = cleanup;
            } else {
                this.boundElements.set(element, { [sortableId]: cleanup });
            }
        };

        const cleanup = () => {
            const boundElement = this.boundElements.get(element);
            if (boundElement?.[sortableId] === cleanup) {
                delete boundElement[sortableId];
                if (Reflect.ownKeys(boundElement).length === 0) {
                    this.boundElements.delete(element);
                }
            }
            log.logic("sortable cleanup", () => ({
                sortableId: String(sortableId),
                wasEnabled: enabled,
            }));
            enabled = false;
            enabledTeardowns.splice(0).forEach((fn) => fn());
            hookTeardowns.forEach((fn) => fn());
        };

        const setupHooks = {
            wrapState: proxy,
            throttle: throttleForAnimation,
            setup: (
                /** @type {Function} */ setupFn,
                /** @type {() => any[]} */ dependenciesFn,
            ) => setupFunctions.set(setupFn, dependenciesFn),
            teardown: (/** @type {Function} */ fn) => hookTeardowns.push(fn),
        };

        useSortable(/** @type {any} */ ({ setupHooks, ...hookParams }));
        bind();

        return {
            enable() {
                const bound = boundTo();
                if (!enabled) {
                    if (bound && bound !== cleanup) {
                        throw new Error(
                            "sortable service: enable() after cleanup() while another " +
                                "sortable holds this element and sortableId",
                        );
                    }
                    log.logic("sortable enable", () => ({
                        sortableId: String(sortableId),
                        rebind: !bound,
                    }));
                    enabled = true;
                    bind();
                    setupFunctions.forEach((dependenciesFn, setupFn) => {
                        const teardown = setupFn(...dependenciesFn());
                        if (typeof teardown === "function") {
                            enabledTeardowns.push(teardown);
                        }
                    });
                }
                return {
                    cleanup,
                };
            },
        };
    }
}

const sortableService = {
    /** @returns {SortableService} */
    start() {
        return new SortableService();
    },
};

registry.category("services").add("sortable", sortableService);
