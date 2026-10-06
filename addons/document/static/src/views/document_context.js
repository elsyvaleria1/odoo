/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("document/views/document_context");

/** @param {Record<string, any>} context */
export function provideDocumentContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
/** @returns {Record<string, any>} */
export function useDocumentContext() {
    return envScope.use();
}
