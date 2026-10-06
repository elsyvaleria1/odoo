// @ts-check
/** @odoo-module native */

import { App, EventBus } from "@odoo/owl";
import { AppContextPlugin } from "@web/core/app_context";
import { isCtrlOrCmdKey } from "@web/core/browser/hotkeys";
import { makeLogger } from "@web/core/debug/debug_logger";
import { AppEvent } from "@web/core/events";
import { ServiceContainer } from "@web/core/service_container";
import {
    getCompiledDevTemplate,
    getCompiledTemplate,
    getTemplate,
} from "@web/core/templates";
import { appTranslateFn } from "@web/core/translation";
import { componentLog, makeAssetLog } from "@web/core/utils/asset_log";
import { session } from "@web/session";

const log = makeAssetLog("env");
/**
 * A component mounted with the web environment may require its services,
 * while a reusable Owl component may only expose the base environment.
 * @template [P=any]
 * @typedef {new (props: P, env: OdooEnv) => import("@odoo/owl").Component<P>} OdooComponentConstructor
 */

/**
 * @typedef {{
 * bus: EventBus;
 * debug: string;
 * services: import("services").ServiceFactories;
 * readonly isSmall: boolean;
 * config?: Record<string, any>;
 * [key: string]: any;
 * }} OdooEnv
 */

const debugLog = makeLogger("web.env");

/** @returns {OdooEnv} */
export function makeEnv() {
    debugLog.lifecycle("makeEnv", () => ({ debug: odoo.debug }));
    log("makeEnv: creating OdooEnv — debug=", odoo.debug || "(empty)");
    const bus = new EventBus();
    const prom = new Promise((resolve) => {
        bus.addEventListener(AppEvent.SERVICES_LOADED, resolve, { once: true });
    });
    const env = /** @type {any} */ ({
        bus,
        isReady: prom,
        services: {},
        debug: odoo.debug,
        get isSmall() {
            throw new Error("UI service not initialized!");
        },
        destroy() {
            serviceContainerOf(env).destroy();
        },
    });
    containersByServices.set(env.services, new ServiceContainer(env));
    return env;
}

/** @type {WeakMap<object, ServiceContainer>} */
const containersByServices = new WeakMap();

/**
 * @param {Record<string, any>} env
 * @returns {ServiceContainer}
 */
export function serviceContainerOf(env) {
    for (
        let services = env.services;
        services;
        services = Object.getPrototypeOf(services)
    ) {
        const container = containersByServices.get(services);
        if (container) {
            return container;
        }
    }
    throw new Error(
        "This env's services were not made by makeEnv(): it has no service container",
    );
}

/**
 * @param {OdooEnv} env
 * @returns {Promise<void>}
 */
export function startServices(env) {
    return serviceContainerOf(env).start();
}

/**
 * @param {OdooEnv} env
 * @returns {Promise<void>}
 */
export function startMissingServices(env) {
    return serviceContainerOf(env).startMissing();
}

const TRANSLATABLE_ATTRIBUTES = ["data-tooltip"];

export const customDirectives = {
    click: (node, value, modifiers) => {
        let mods = "";
        if (modifiers.includes("synthetic")) {
            mods += ".synthetic";
        }
        if (modifiers.includes("capture")) {
            mods += ".capture";
        }
        const hasStop = modifiers.includes("stop");
        const hasPrevent = modifiers.includes("prevent");
        const handlerFunction = `(ev) => __globals__.click(ev, (${value}).bind(this), ${hasStop}, ${hasPrevent})`;
        node.setAttribute(`t-on-click${mods}`, handlerFunction);
        node.setAttribute(`t-on-auxclick${mods}`, handlerFunction);
    },
};

export const globalValues = {
    /**
     * @param {MouseEvent} ev
     * @param {Function} value
     * @param {boolean} hasStop
     * @param {boolean} hasPrevent
     */
    click: (ev, value, hasStop, hasPrevent) => {
        if (ev.button === 0 || ev.button === 1) {
            if (hasStop) {
                ev.stopPropagation();
            }
            if (hasPrevent) {
                ev.preventDefault();
            }
            const ctrlKey = isCtrlOrCmdKey(ev);
            const isMiddleClick = (ctrlKey && ev.button === 0) || ev.button === 1;
            return value(ev, isMiddleClick);
        }
    },
};

/**
 * @param {{ customDirectives?: Record<string, Function>, globalValues?: Record<string, any> }} extension
 */
export function extendTemplateLanguage(extension) {
    for (const [target, added] of [
        [customDirectives, extension.customDirectives || {}],
        [globalValues, extension.globalValues || {}],
    ]) {
        for (const [name, value] of Object.entries(added)) {
            if (name in target && target[name] !== value) {
                throw new Error(`the template language already defines "${name}"`);
            }
            target[name] = value;
        }
    }
}

/** @type {import("@web/core/service_container").ServiceContext | null} */
let rootAppContext = null;

/** @returns {import("@web/core/service_container").ServiceContext | null} */
export function getRootAppContext() {
    return rootAppContext;
}

/** @param {import("@web/core/service_container").ServiceContext} appContext */
export function setRootAppContext(appContext) {
    rootAppContext = appContext;
}

/**
 * @param {import("@web/core/service_container").ServiceContext | undefined} appContext
 * @param {Record<string, any>} [overrides]
 * @returns {Record<string, any>}
 */
export function makeAppConfig(appContext, overrides = {}) {
    /** @type {Record<string, any>} */
    const config = {
        getTemplate,
        dev: Boolean(/** @type {any} */ (appContext)?.debug || session.test_mode),
        translatableAttributes: TRANSLATABLE_ATTRIBUTES,
        translateFn: appTranslateFn,
        customDirectives,
        globalValues,
        plugins: appContext ? [AppContextPlugin] : [],
        config: appContext ? { appContext } : {},
        ...overrides,
    };
    if (
        config.getTemplate === getTemplate &&
        config.translatableAttributes === TRANSLATABLE_ATTRIBUTES &&
        config.translateFn === appTranslateFn &&
        config.customDirectives === customDirectives &&
        config.globalValues === globalValues
    ) {
        // compiled ahead of time with exactly these options
        config.getTemplate = config.dev ? getCompiledDevTemplate : getCompiledTemplate;
    }
    return config;
}

/**
 * @param {import("@odoo/owl").ComponentConstructor} component
 * @param {HTMLElement | ShadowRoot} target
 * @param {Record<string, any> & {
 * env?: OdooEnv,
 * props?: Record<string, any>,
 * beforeMount?: (env: OdooEnv) => void | Promise<void>
 * }} [appConfig]
 */
export async function mountComponent(component, target, appConfig = {}) {
    const { beforeMount, props, env: givenEnv, ...owlConfig } = appConfig;
    let env = givenEnv;
    const isRoot = !env;
    log(
        "mountComponent:",
        component.name || "anon",
        "isRoot=",
        isRoot,
        "target=",
        "tagName" in target ? target.tagName : "#shadow-root",
    );
    if (isRoot) {
        env = makeEnv();
        await startServices(/** @type {OdooEnv} */ (env));
    }
    const endMount = debugLog.perf(`mount ${component.name || "anon"}`);
    const app = new App(
        makeAppConfig(/** @type {any} */ (env), { name: component.name, ...owlConfig }),
    );
    if (isRoot) {
        setRootAppContext(/** @type {any} */ (env));
        if (!(/** @type {any} */ (app).dev)) {
            /** @type {any} */ (env).services.template_compile_cache?.install(app);
        }
    }
    await beforeMount?.(/** @type {OdooEnv} */ (env));
    componentLog("mount", component.name || "anon", "isRoot=", isRoot);
    const root = await app.createRoot(component, { props }).mount(target);
    endMount({ isRoot });
    if (isRoot) {
        /** @type {any} */ (odoo).__WOWL_DEBUG__ = { root };
    }
    return app;
}
