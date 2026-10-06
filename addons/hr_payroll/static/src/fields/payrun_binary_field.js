/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { BinaryField, binaryField } from "@web/fields/media/binary/binary_field";

export class PayRunBinaryField extends BinaryField {
    static template = "hr_payroll.PayRunBinaryField";
    static props = { ...BinaryField.props, formatField: t.string().optional() };

    get format() {
        return this.props.record.data[this.props.formatField] || "";
    }
}

export const payRunBinaryField = {
    ...binaryField,
    component: PayRunBinaryField,
    extractProps: ({ attrs, options }) => ({
        ...binaryField.extractProps({ attrs, options }),
        formatField: attrs.format,
    }),
};

registry.category("fields").add("payrun_binary", payRunBinaryField);
