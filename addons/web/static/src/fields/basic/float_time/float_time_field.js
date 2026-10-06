// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { formatFloatTime } from "@web/core/formatters";
import { parseFloatTime } from "@web/core/parsers";
import { _t } from "@web/core/translation";
import { registerField } from "@web/fields/_registry";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { NumericInputFieldBase } from "../numeric_input_field_base.js";

export class FloatTimeField extends NumericInputFieldBase {
    static template = "web.FloatTimeField";
    static props = { ...standardFieldProps, displaySeconds: t.boolean().optional() };

    /**
     * @param {string} v
     * @returns {number}
     */
    parse(v) {
        return parseFloatTime(v);
    }

    /**
     * @param {boolean} _humanReadable
     * @returns {string}
     */
    formatValue(_humanReadable) {
        return formatFloatTime(this.value, {
            displaySeconds: this.props.displaySeconds,
        });
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
export const floatTimeField = {
    component: FloatTimeField,
    displayName: _t("Time"),
    supportedOptions: [
        {
            label: _t("Display seconds"),
            name: "display_seconds",
            type: "boolean",
        },
    ],
    supportedTypes: ["float"],
    isEmpty: () => false,
    extractProps: formatFloatTime.extractOptions,
};

registerField("float_time", floatTimeField);
