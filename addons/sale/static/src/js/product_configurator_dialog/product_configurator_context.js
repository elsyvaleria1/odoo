/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope(
    "sale/js/product_configurator_dialog/product_configurator_context",
);

/** @param {Record<string, any>} context */
export function provideProductConfiguratorContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildProductConfiguratorContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useProductConfiguratorContext() {
    return envScope.use();
}
