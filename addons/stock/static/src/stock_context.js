/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("stock/stock_context");

/** @param {Record<string, any>} context */
export function provideStockContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildStockContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useStockContext() {
    return envScope.use();
}
