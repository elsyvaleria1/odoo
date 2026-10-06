/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope(
    "web_studio/client_action/view_editor/view_editor_model_context",
);

/** @param {import("./view_editor_model").ViewEditorModel} viewEditorModel */
export function provideViewEditorModel(viewEditorModel) {
    envScope.provide({ viewEditorModel });
}

/** @returns {import("./view_editor_model").ViewEditorModel} */
export function useCurrentViewEditorModel() {
    return envScope.use().viewEditorModel;
}
