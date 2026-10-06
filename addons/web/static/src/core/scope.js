// @ts-check
/** @odoo-module native */

import { Plugin, providePlugins, useConfig, useScope } from "@odoo/owl";

const EMPTY = Object.freeze({});

/** @typedef {import("@web/core/service_container").ServiceContext} AppContext */

export class AppContextPlugin extends Plugin {
    static id = "web.app_context";
    /** @type {AppContext} */
    context = useConfig("appContext");
}

/**
 * @template {import("@odoo/owl").PluginConstructor} P
 * @param {P} PluginClass
 * @returns {InstanceType<P> | null}
 */
function findPlugin(PluginClass, pluginManager = useScope().pluginManager) {
    return pluginManager.getPlugin(PluginClass);
}

// a scope nobody provides reads the application context, as an OWL 2 sub-env read the root env
function appContextOrEmpty(/** @type {any} */ pluginManager) {
    return findPlugin(AppContextPlugin, pluginManager)?.context ?? EMPTY;
}

/**
 * @template {Record<string, any>} [T=Record<string, any>]
 * @param {string} id
 * @param {{ root?: (pluginManager?: any) => Record<string, any> }} [options]
 */
export function defineScope(id, { root = appContextOrEmpty } = {}) {
    class ScopePlugin extends Plugin {
        static id = `web.scope.${id}`;
        value = useConfig("value");
    }
    /** @returns {T} */
    function use() {
        const plugin = findPlugin(ScopePlugin);
        return /** @type {T} */ (plugin ? plugin.value : root());
    }
    /**
     * @param {Partial<T>} values
     * @returns {T}
     */
    function provide(values) {
        // a child scope sees every key of its parent, as OWL 2's sub-env did
        const value = Object.defineProperties(
            Object.create(use()),
            Object.getOwnPropertyDescriptors(values),
        );
        providePlugins([ScopePlugin], { value });
        return value;
    }
    /**
     * @param {any} component
     * @returns {T} the value `component` sees, read outside any hook, as
     * OWL 2's `component.env` could be
     */
    function readFrom(component) {
        const pluginManager =
            component?.__owl__?.pluginManager ?? component?.pluginManager;
        if (!pluginManager) {
            return /** @type {T} */ (EMPTY);
        }
        const plugin = findPlugin(ScopePlugin, pluginManager);
        return /** @type {T} */ (plugin ? plugin.value : root(pluginManager));
    }
    return { use, provide, readFrom, Plugin: ScopePlugin };
}
