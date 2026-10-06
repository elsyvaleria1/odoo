/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("pos_self_order/app/pos_self_order_context");

/** @param {Record<string, any>} context */
export function providePosSelfOrderContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildPosSelfOrderContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function usePosSelfOrderContext() {
    return envScope.use();
}
