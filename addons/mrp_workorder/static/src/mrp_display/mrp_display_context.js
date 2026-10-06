/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("mrp_workorder/mrp_display/mrp_display_context");

/** @param {Record<string, any>} context */
export function provideMrpDisplayContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildMrpDisplayContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useMrpDisplayContext() {
    return envScope.use();
}
