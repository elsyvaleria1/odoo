// @ts-check
/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web/core/web_context_hooks");

/** @param {Record<string, any>} context */
export function provideWebContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildWebContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useWebContext() {
    return envScope.use();
}
