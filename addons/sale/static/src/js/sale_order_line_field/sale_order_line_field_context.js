/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope(
    "sale/js/sale_order_line_field/sale_order_line_field_context",
);

/** @param {Record<string, any>} context */
export function provideSaleOrderLineFieldContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildSaleOrderLineFieldContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useSaleOrderLineFieldContext() {
    return envScope.use();
}
