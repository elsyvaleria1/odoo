/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    BooleanIconField,
    booleanIconField,
} from "@web/fields/basic/boolean_icon/boolean_icon_field";

export class DocumentsBooleanIconField extends BooleanIconField {
    static template = "document.DocumentsBooleanIconField";
    static props = {
        ...BooleanIconField.props,
        btnTrueClass: t.string().optional(),
        btnFalseClass: t.string().optional(),
    };
}

export const documentsBooleanIconField = {
    ...booleanIconField,
    component: DocumentsBooleanIconField,
    extractProps: (...args) => {
        const [{ options }] = args;
        return {
            ...booleanIconField.extractProps(...args),
            btnTrueClass: options.btn_true_class,
            btnFalseClass: options.btn_false_class,
        };
    },
};

registry.category("fields").add("documents_boolean_icon", documentsBooleanIconField);
