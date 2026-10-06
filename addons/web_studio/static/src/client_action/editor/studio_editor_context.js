/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("web_studio/client_action/editor/studio_editor_context");

/** @param {Record<string, any>} context */
export function provideStudioEditorContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildStudioEditorContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useStudioEditorContext() {
    return envScope.use();
}
