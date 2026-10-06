/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("html_editor/html_editor_context");

/** @param {Record<string, any>} context */
export function provideHtmlEditorContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildHtmlEditorContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useHtmlEditorContext() {
    return envScope.use();
}
