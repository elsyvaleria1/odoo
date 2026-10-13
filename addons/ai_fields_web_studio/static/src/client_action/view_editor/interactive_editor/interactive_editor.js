/** @odoo-module native */
import { AiFieldConfigurationDialog } from "@ai_fields_web_studio/client_action/view_editor/interactive_editor/field_configuration/ai_field_configuration_dialog";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { NewFields } from "@web_studio/client_action/view_editor/editors/components/view_fields";
import { InteractiveEditor } from "@web_studio/client_action/view_editor/interactive_editor/interactive_editor";

patch(NewFields.prototype, {
    get newFieldsComponents() {
        return [
            ...super.newFieldsComponents,
            {
                classType: "ai",
                type: "AI",
                string: _t("AI Field"),
                name: "ai",
                dropData: JSON.stringify({ ai: true }),
            },
        ];
    },
});

patch(InteractiveEditor.prototype, {
    async getNewFieldNode(data) {
        if (!data.ai) {
            return super.getNewFieldNode(data);
        }
        return await new Promise((resolve) => {
            this.addDialog(AiFieldConfigurationDialog, {
                cancel: () => {},
                confirm: (nodeData) => resolve(nodeData),
                propertiesModel: this.viewEditorModel.resModel,
            });
        });
    },
});
