/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope("html_editor/core/editor_overlay_context");

/** @param {Record<string, any>} context */
export function provideEditorOverlayContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildEditorOverlayContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useEditorOverlayContext() {
    return envScope.use();
}
