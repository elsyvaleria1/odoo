/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useFieldDirtySignal } from "@web/fields/field_dirty_signal";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { AiPrompt } from "./ai_prompt.js";

export class AiPromptField extends Component {
    static template = "ai.AiPromptField";
    static props = {
        ...standardFieldProps,
        modelReferenceField: t.string(),
        fieldReferenceField: t.string().optional(),
        placeholder: t.string().optional(),
        recordSelectorRelationField: t.string().optional(),
        recordSelectorDomain: t.string().optional(),
        showMissingRecordsWarning: t.any().optional(),
    };
    static components = { AiPrompt };
    props = useProps(this.constructor.props);

    setup() {
        // Owned dirty-signal emitter (own owner symbol, cleared on destroy):
        // a raw boolean trigger would share the legacy owner with every other
        // unconverted field and clobber their dirty state.
        this.setFieldDirty = useFieldDirtySignal();
    }

    get updatedFieldName() {
        return this.props.record.data[this.props.fieldReferenceField];
    }

    get recordSelectorRelation() {
        return this.props.record.data[this.props.recordSelectorRelationField];
    }

    get missingRecordsMessage() {
        return _t("Insert records the AI can use with the '/record' command");
    }

    get modelName() {
        return this.props.record.data[this.props.modelReferenceField];
    }

    get prompt() {
        return this.props.record.data[this.props.name] || "";
    }

    onChange() {
        this.setFieldDirty(true);
    }

    updatePrompt(value) {
        if (value !== this.prompt) {
            this.props.record.update({ [this.props.name]: value });
        }
        // The editor content is now committed to the record: whatever
        // dirtiness remains is the record's, not this input's.
        this.setFieldDirty(false);
    }
}

export const aiPrompt = {
    component: AiPromptField,
    supportedTypes: ["html"],
    additionalClasses: ["d-inline"],

    extractProps: ({ attrs, options }) => ({
        placeholder: attrs.placeholder,
        modelReferenceField: options.model_reference_field,
        fieldReferenceField: options.field_reference_field,
        recordSelectorRelationField: options.record_selector_relation_field,
        recordSelectorDomain: options.record_selector_domain,
        showMissingRecordsWarning: Boolean(options.show_missing_records_warning),
    }),
};

registry.category("fields").add("ai_prompt", aiPrompt);
