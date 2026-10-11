/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { BooleanField, booleanField } from "@web/fields/basic/boolean/boolean_field";

export class BooleanUpdateFlagField extends BooleanField {
    static props = {
        ...BooleanField.props,
        flagFieldName: t.string(),
        referenceValue: t.boolean(),
    };
    /**
     * @override
     */
    async onChange(newValue) {
        super.onChange(...arguments);
        await this.props.record.update({
            [this.props.flagFieldName]: newValue !== this.props.referenceValue,
        });
    }
}

export const booleanUpdateFlagField = {
    ...booleanField,
    component: BooleanUpdateFlagField,
    displayName: _t("Checkbox updating comparison flag"),
    extractProps({ options }, { context: { referenceValue } }) {
        return {
            flagFieldName: options.flagFieldName,
            referenceValue: referenceValue,
        };
    },
};

registry.category("fields").add("boolean_update_flag", booleanUpdateFlagField);
