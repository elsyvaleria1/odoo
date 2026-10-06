// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useInputField } from "@web/fields/input_field_hook";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { TrimmingInputFieldBase } from "./trimming_input_field_base.js";

export class SimpleInputFieldBase extends TrimmingInputFieldBase {
    static props = {
        ...standardFieldProps,
        placeholder: t.string().optional(),
        required: t.boolean().optional(),
    };

    setup() {
        this.inputRef = elementRef(HTMLInputElement);
        useInputField({
            ref: this.inputRef,
            getValue: () => this.value,
            parse: (v) => this.parse(v),
        });
    }

    /** @returns {string} */
    get value() {
        return this.field.value || "";
    }
}
