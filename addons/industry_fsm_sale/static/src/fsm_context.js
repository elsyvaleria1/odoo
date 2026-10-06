/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("industry_fsm_sale/fsm_context");

/** @param {Record<string, any>} context */
export function provideFsmContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildFsmContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useFsmContext() {
    return envScope.use();
}
