/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    SelectionField,
    selectionField,
} from "@web/fields/selection/selection/selection_field";

export class StakeholderScoreSelectionField extends SelectionField {
    static props = { ...SelectionField.props, relatedFieldName: t.string() };

    onChange(value) {
        super.onChange(value);
        const relatedFieldName = this.props.relatedFieldName;
        if (
            !this.props.record.data[relatedFieldName] &&
            this.props.record.data[this.props.name] !== value
        ) {
            this.props.record.update({ [relatedFieldName]: true });
        }
    }
}

registry.category("fields").add("stakeholder_score_selection", {
    ...selectionField,
    component: StakeholderScoreSelectionField,
    extractProps: ({ options }) => ({
        relatedFieldName: options.related_field_name,
    }),
});
