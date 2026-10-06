/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("mrp_mps/mrp_mps_context");

/** @param {Record<string, any>} context */
export function provideMrpMpsContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildMrpMpsContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useMrpMpsContext() {
    return envScope.use();
}
