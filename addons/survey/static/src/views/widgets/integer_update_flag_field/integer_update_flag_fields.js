/** @odoo-module native */
import { t } from "@odoo/owl";
import { ParseError } from "@web/core/parse_error";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { IntegerField, integerField } from "@web/fields/basic/integer/integer_field";

export class IntegerUpdateFlagField extends IntegerField {
    static props = {
        ...IntegerField.props,
        flagFieldName: t.string(),
        referenceValue: t.number(),
    };
    /**
     * @override
     */
    setup() {
        super.setup(...arguments);
        const inputRef = (this.inputRef = this.numpadDecimalRef);
        const onChange = async (ev) => {
            let value;
            try {
                value = this.parse(ev.target.value);
            } catch (error) {
                if (error instanceof ParseError) {
                    return;
                }
                throw error;
            }
            await this.props.record.update({
                [this.props.flagFieldName]: value !== this.props.referenceValue,
            });
        };
        useLayoutEffect(
            (inputEl) => {
                if (inputEl) {
                    inputEl.addEventListener("change", onChange);
                    return () => {
                        inputEl.removeEventListener("change", onChange);
                    };
                }
            },
            () => [inputRef.el],
        );
    }
}

export const integerUpdateFlagField = {
    ...integerField,
    component: IntegerUpdateFlagField,
    displayName: _t("Integer updating comparison flag"),
    extractProps({ attrs, options }, { context: { referenceValue } }) {
        return {
            ...integerField.extractProps(...arguments),
            flagFieldName: options.flagFieldName,
            referenceValue: referenceValue,
        };
    },
};

registry.category("fields").add("integer_update_flag", integerUpdateFlagField);
