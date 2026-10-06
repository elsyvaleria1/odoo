/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("api_doc/doc_model_store_context");

/** @param {Record<string, any>} context */
export function provideDocModelStore(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildDocModelStore(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useDocModelStore() {
    return envScope.use();
}
