/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("product/product_catalog/product_catalog_context");

/** @param {Record<string, any>} context */
export function provideProductCatalogContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildProductCatalogContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useProductCatalogContext() {
    return envScope.use();
}
