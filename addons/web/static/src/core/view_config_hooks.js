// @ts-check
/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web/core/view_config_hooks");

/** @param {import("@web/views/view_config").ViewConfig & Record<string, any>} config */
export function provideViewConfig(config) {
    envScope.provide({ config });
}

/** @param {Partial<import("@web/views/view_config").ViewConfig> & Record<string, any>} config */
export function provideChildViewConfig(config) {
    envScope.provide({ config });
}

/** @returns {import("@web/views/view_config").ViewConfig & Record<string, any>} */
export function useViewConfig() {
    return envScope.use().config;
}

/** @param {any} component */
export function viewConfigOf(component) {
    return envScope.readFrom(component).config;
}
