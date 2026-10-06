/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { RadioField, radioField } from "@web/fields/selection/radio/radio_field";

export class RadioSelectionFieldWithFilter extends RadioField {
    static props = { ...RadioField.props, allowedSelectionField: t.string() };

    get items() {
        const allowedItems = this.props.record.data[this.props.allowedSelectionField];
        return super.items.filter(([value]) => (allowedItems || []).includes(value));
    }
}

export const radioSelectionFieldWithFilter = {
    ...radioField,
    component: RadioSelectionFieldWithFilter,
    displayName: _t("Radio for Selection With Filter"),
    supportedTypes: ["selection"],
    extractProps({ options }) {
        return {
            ...radioField.extractProps(...arguments),
            allowedSelectionField: options.allowed_selection_field,
        };
    },
};

registry
    .category("fields")
    .add("radio_selection_with_filter", radioSelectionFieldWithFilter);
