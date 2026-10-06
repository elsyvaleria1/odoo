// @ts-check
/** @odoo-module native */

import { useScope } from "@odoo/owl";
import { AppContextPlugin, defineScope } from "@web/core/scope";

export { AppContextPlugin };

/** @typedef {import("@web/core/service_container").ServiceContext} AppContext */

function rootAppContext(pluginManager = useScope().pluginManager) {
    const plugin = pluginManager.getPlugin(AppContextPlugin);
    if (!plugin) {
        throw new Error(
            "No application context: the component was not mounted by mountComponent()",
        );
    }
    return plugin.context;
}

// services, bus and debug context a subtree overrides (provideServices, provideEventBus,
// provideDebugContext) shadow the application's own, key by key
export const appScope = defineScope("web.app", { root: rootAppContext });

/** @returns {AppContext} */
export function useAppContext() {
    return /** @type {AppContext} */ (appScope.use());
}

/**
 * @param {any} component
 * @returns {AppContext}
 */
export function appContextOf(component) {
    return /** @type {AppContext} */ (appScope.readFrom(component));
}
