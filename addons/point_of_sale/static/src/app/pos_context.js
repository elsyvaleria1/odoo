/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("point_of_sale/app/pos_context");

/** @param {Record<string, any>} context */
export function providePosContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildPosContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function usePosContext() {
    return envScope.use();
}
