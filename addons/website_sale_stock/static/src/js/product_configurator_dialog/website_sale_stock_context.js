/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope(
    "website_sale_stock/js/product_configurator_dialog/website_sale_stock_context",
);

/** @param {Record<string, any>} context */
export function provideWebsiteSaleStockContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildWebsiteSaleStockContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useWebsiteSaleStockContext() {
    return envScope.use();
}
