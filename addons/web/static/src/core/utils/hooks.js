// @ts-check
/** @odoo-module native */

import {
    onMounted,
    onPatched,
    onWillDestroy,
    onWillUnmount,
    proxy,
    toRaw,
    useEffect,
    useProps,
} from "@odoo/owl";
import { appScope } from "@web/core/app_context";
import { isMobileOS } from "@web/core/browser/feature_detection";
import { inputModality } from "@web/core/input_modality";
import { getActiveElement } from "@web/core/utils/dom/ui";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

/** @typedef {{ readonly el: HTMLElement | null; }} Ref */

/**
 * @param {Object} params
 * @param {Ref} params.ref
 * @param {boolean} [params.selectAll]
 * @param {boolean} [params.mobile]
 * @returns {Ref}
 */
export function useAutofocus({ ref, selectAll, mobile }) {
    const uiService = useService("ui");

    function isFocusable(/** @type {HTMLElement | null} */ el) {
        if (!el) {
            return false;
        }
        if (!uiService.activeElement || uiService.activeElement.contains(el)) {
            return true;
        }
        const rootNode = el.getRootNode();
        return (
            rootNode instanceof ShadowRoot &&
            uiService.activeElement.contains(rootNode.host)
        );
    }
    useLayoutEffect(
        (el) => {
            if (!mobile && (inputModality.isTouch || isMobileOS())) {
                return;
            }
            if (isFocusable(el)) {
                el.focus();
                if (
                    ["INPUT", "TEXTAREA"].includes(el.tagName) &&
                    /** @type {HTMLInputElement} */ (el).type !== "number"
                ) {
                    const input = /** @type {HTMLInputElement} */ (el);
                    input.selectionEnd = input.value.length;
                    input.selectionStart = selectAll ? 0 : input.value.length;
                }
            }
        },
        () => [ref.el],
    );
    return ref;
}

/** @param {Record<string, any>} services */
export function provideServices(services) {
    appScope.provide({ services });
}

/** @returns {Record<string, any>} */
export function useServices() {
    return appScope.use().services;
}

/** @param {import("@odoo/owl").EventBus} bus */
export function provideEventBus(bus) {
    appScope.provide({ bus });
}

/** @returns {import("@odoo/owl").EventBus} */
export function useEventBus() {
    return appScope.use().bus;
}

/**
 * @param {import("@odoo/owl").EventBus} bus
 * @param {string} eventName
 * @param {(ev: CustomEvent<any>) => void} callback
 * @returns {void}
 */
export function useBus(bus, eventName, callback) {
    useLayoutEffect(
        () => {
            const listener = /** @type {EventListener} */ (callback);
            bus.addEventListener(eventName, listener);
            return () => bus.removeEventListener(eventName, listener);
        },
        () => [],
    );
}

export const useServiceProtectMethodHandling = {
    /** @returns {Promise<never>} */
    fn() {
        return this.original();
    },
    /** @returns {Promise<never>} */
    mocked() {
        return new Promise(() => {});
    },
    /** @returns {Promise<never>} */
    original() {
        return Promise.reject(new Error("Component is destroyed"));
    },
};

/**
 * @param {() => boolean} isDestroyed
 * @param {() => Function} resolve
 * @returns {Function}
 */
function _protectMethod(isDestroyed, resolve) {
    return function (/** @type {any[]} */ ...args) {
        if (isDestroyed()) {
            return useServiceProtectMethodHandling.fn();
        }

        const prom = Promise.resolve(resolve().call(this, ...args));
        const protectedProm = prom.then(
            (result) => (isDestroyed() ? new Promise(() => {}) : result),
            (error) => {
                if (!isDestroyed()) {
                    throw error;
                }
                console.warn(
                    "Discarded a service call that failed after its component was destroyed:",
                    error,
                );
                return new Promise(() => {});
            },
        );
        return Object.assign(protectedProm, {
            abort: /** @type {any} */ (prom).abort,
            cancel: /** @type {any} */ (prom).cancel,
        });
    };
}

/** @returns {() => boolean} */
export function useIsMounted() {
    let mounted = false;
    onMounted(() => {
        mounted = true;
    });
    onWillUnmount(() => {
        mounted = false;
    });
    return () => mounted;
}

/** @returns {() => boolean} */
export function useIsDestroyed() {
    let destroyed = false;
    onWillDestroy(() => {
        destroyed = true;
    });
    return () => destroyed;
}

/** @type {WeakMap<string[], Set<PropertyKey>>} */
const guardedMethodSets = new WeakMap();

/**
 * @param {string[]} methods
 * @returns {Set<PropertyKey>}
 */
function guardedMethodSet(methods) {
    let set = guardedMethodSets.get(methods);
    if (!set) {
        set = new Set(methods);
        guardedMethodSets.set(methods, set);
    }
    return set;
}

/**
 * @param {() => boolean} isDestroyed
 * @param {any} observed
 * @param {string[]} methods
 * @returns {any}
 */
function makeGuardedView(isDestroyed, observed, methods) {
    const methodSet = guardedMethodSet(methods);
    /** @type {Map<PropertyKey, Function>} */
    const guarded = new Map();
    return new Proxy(observed, {
        get(target, property) {
            if (methodSet.has(property)) {
                let fn = guarded.get(property);
                if (!fn) {
                    fn = _protectMethod(isDestroyed, () => observed[property]);
                    guarded.set(property, fn);
                }
                return fn;
            }
            const value = Reflect.get(target, property, target);
            if (
                value !== null &&
                typeof value === "object" &&
                Object.getPrototypeOf(value) === target
            ) {
                return makeGuardedView(isDestroyed, value, methods);
            }
            return value;
        },
    });
}

/** @type {Record<string, string[]>} */
export const SERVICES_METADATA = {};

/**
 * @template {keyof import("services").ServiceFactories} K
 * @param {K} serviceName
 * @returns {import("services").ServiceFactories[K]}
 */
export function useService(serviceName) {
    const service = _useService(serviceName, false);
    return /** @type {import("services").ServiceFactories[K]} */ (service);
}

/**
 * @template {keyof import("services").ServiceFactories} K
 * @param {K} serviceName
 * @returns {import("services").ServiceFactories[K] | null}
 */
export function useOptionalService(serviceName) {
    return /** @type {any} */ (_useService(serviceName, true));
}

/**
 * @param {string} serviceName
 * @param {boolean} optional
 * @returns {any}
 */
function _useService(serviceName, optional) {
    const services = useServices();
    if (!(serviceName in services)) {
        if (optional) {
            return null;
        }
        throw new Error(`Service ${serviceName} is not available`);
    }
    const service = services[serviceName];
    const observed =
        toRaw(service) !== service
            ? /** @type {any} */ (proxy(/** @type {any} */ (service)))
            : service;
    if (SERVICES_METADATA[serviceName]) {
        if (service instanceof Function) {
            return _protectMethod(useIsDestroyed(), () => services[serviceName]);
        }
        return makeGuardedView(
            useIsDestroyed(),
            observed,
            SERVICES_METADATA[serviceName],
        );
    }
    return observed;
}

/**
 * @param {{ ref: Ref }} params
 * @returns {void}
 */
export function useSpellCheck({ ref }) {
    function toggleSpellcheck(/** @type {Event} */ ev) {
        /** @type {HTMLElement} */ (ev.target).spellcheck =
            getActiveElement(/** @type {Node} */ (ev.target)) === ev.target;
    }
    useLayoutEffect(
        (el) => {
            /** @type {Element[]} */
            const elements = [];
            if (el) {
                const inputs =
                    ["INPUT", "TEXTAREA"].includes(el.nodeName) || el.isContentEditable
                        ? [el]
                        : el.querySelectorAll(
                              "input, textarea, [contenteditable=true]",
                          );
                inputs.forEach((/** @type {Element} */ input) => {
                    if (/** @type {HTMLElement} */ (input).spellcheck !== false) {
                        elements.push(input);
                        input.addEventListener("focus", toggleSpellcheck);
                        input.addEventListener("blur", toggleSpellcheck);
                    }
                });
            }
            return () => {
                elements.forEach((input) => {
                    input.removeEventListener("focus", toggleSpellcheck);
                    input.removeEventListener("blur", toggleSpellcheck);
                });
            };
        },
        () => [ref.el],
    );
}

/**
 * @typedef {((ref: Ref) => void) & { readonly el: HTMLElement | null }} ForwardRef
 * @property {HTMLElement | undefined} el
 */

/**
 * @param {() => HTMLInputElement | null | undefined} getElement
 * @param {() => any} getValue
 * @param {{ property?: "value" | "checked" }} [options]
 * @returns {() => boolean}
 */
export function useSyncedInputProperty(
    getElement,
    getValue,
    { property = "value" } = {},
) {
    const sync = () => {
        const element = getElement();
        const value = getValue();
        if (!element || value === undefined || element[property] === value) {
            return false;
        }
        if (property === "checked") {
            element.checked = Boolean(value);
        } else {
            element.value = value;
        }
        return true;
    };
    // what sync reads is tracked: a component whose template does not read the
    // value is not re-rendered, hence not patched, when only the value changed
    useEffect(() => {
        sync();
    });
    onPatched(sync);
    return sync;
}

/** @returns {ForwardRef} */
export function useChildRef() {
    let defined = false;
    /** @type {Ref} */
    let value;
    return /** @type {ForwardRef} */ (
        function ref(/** @type {Ref} */ v) {
            value = v;
            if (defined) {
                return;
            }
            Object.defineProperty(ref, "el", {
                get() {
                    return value.el;
                },
            });
            defined = true;
        }
    );
}
/**
 * @param {string} refName
 * @param {Ref} ref
 * @returns {Ref}
 */
export function useForwardRefToParent(refName, ref) {
    const props = useProps();
    if (props[refName]) {
        props[refName](ref);
    }
    return ref;
}
/** @returns {(...args: any[]) => () => void} */
export function useOwnedDialogs() {
    const dialogService = useService("dialog");
    const closers = new Set();
    onWillUnmount(() => {
        closers.forEach((close) => close());
        closers.clear();
    });
    const addDialog = (
        /** @type {any} */ dialogClass,
        /** @type {any} */ props,
        /** @type {any} */ options = {},
    ) => {
        const originalOnClose = options.onClose;
        const originalClose = /** @type {any} */ (dialogService).add(
            dialogClass,
            props,
            {
                ...options,
                onClose: (/** @type {any[]} */ ...onCloseArgs) => {
                    closers.delete(wrappedClose);
                    return originalOnClose?.(...onCloseArgs);
                },
            },
        );
        const wrappedClose = () => {
            closers.delete(wrappedClose);
            originalClose();
        };
        closers.add(wrappedClose);
        return wrappedClose;
    };
    return addDialog;
}
/**
 * @param {Ref} ref
 * @param {...any} listener
 * @returns {void}
 */
export function useRefListener(ref, ...listener) {
    const args = /** @type {[string, EventListenerOrEventListenerObject, ...any[]]} */ (
        listener
    );
    useLayoutEffect(
        (el) => {
            el?.addEventListener(...args);
            return () => el?.removeEventListener(...args);
        },
        () => [ref.el],
    );
}

/**
 * @template {string} K
 * @typedef {K extends keyof HTMLElementEventMap
 *     ? HTMLElementEventMap[K]
 *     : K extends keyof WindowEventMap
 *       ? WindowEventMap[K]
 *       : K extends keyof DocumentEventMap
 *         ? DocumentEventMap[K]
 *         : any} ListenedEvent
 */

/**
 * @template {string} K
 * @param {EventTarget} target
 * @param {K} eventName
 * @param {(ev: ListenedEvent<K>) => unknown} handler
 * @param {boolean | AddEventListenerOptions} [eventParams]
 * @returns {void}
 */
export function useMountedListener(target, eventName, handler, eventParams) {
    /** @type {Event | undefined} */
    let attachedDuring;
    const listener = (/** @type {Event} */ ev) => {
        if (ev !== attachedDuring) {
            handler.call(target, /** @type {ListenedEvent<K>} */ (ev));
        }
    };
    onMounted(() => {
        attachedDuring = window.event;
        target.addEventListener(eventName, listener, eventParams);
    });
    onWillUnmount(() => target.removeEventListener(eventName, listener, eventParams));
}

/** @type {Map<string, number>} */
const bodyClassHolders = new Map();

/**
 * Marks `<body>` with `className` while the calling component is mounted.
 *
 * This is how a screen tells the rest of the page that it is on. A stylesheet
 * must not ask the page instead: `body:has(.my_screen) .btn` makes a DOM change
 * anywhere, on any screen, restyle every `.btn` of the document, whereas a class
 * on `<body>` costs one invalidation when the screen opens and one when it
 * closes. Holders are counted, so two components marking the same class do not
 * undo each other.
 *
 * @param {string} className
 * @returns {void}
 */
export function useBodyClass(className) {
    onMounted(() => {
        bodyClassHolders.set(className, (bodyClassHolders.get(className) || 0) + 1);
        document.body.classList.add(className);
    });
    onWillUnmount(() => {
        const holders = (bodyClassHolders.get(className) || 1) - 1;
        if (holders) {
            bodyClassHolders.set(className, holders);
        } else {
            bodyClassHolders.delete(className);
            document.body.classList.remove(className);
        }
    });
}
