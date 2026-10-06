// @ts-check
/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web/core/view_button_context_hooks");

/** @param {Record<string, any>} context */
export function provideViewButtonContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useViewButtonContext() {
    return envScope.use();
}

/**
 * @param {any} component
 * @returns {Record<string, any>} the view-button context the component sees,
 *   its own included, read outside any hook
 */
export function readViewButtonContext(component) {
    return envScope.readFrom(component);
}
