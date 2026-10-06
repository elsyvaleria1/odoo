// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { extractPercentageTrailingZeros, formatPercentage } from "@web/core/formatters";
import { parsePercentage } from "@web/core/parsers";
import { _t } from "@web/core/translation";
import { extractDigits } from "@web/core/utils/format/digits";
import { Operation } from "@web/core/utils/operation";
import { registerField } from "@web/fields/_registry";
import { digitsAttribute, hideTrailingZerosOption } from "@web/fields/field_options";
import { isFalseEmpty, unscaleParsedNumber } from "@web/fields/field_utils";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { NumericInputFieldBase } from "../numeric_input_field_base.js";

export class PercentageField extends NumericInputFieldBase {
    static template = "web.PercentageField";
    static props = {
        ...standardFieldProps,
        digits: t.array().optional(),
        trailingZeros: t.boolean().optional(false),
    };

    /**
     * @param {string} v
     * @returns {number | Operation}
     */
    parse(v) {
        const parsed = parsePercentage(v, { allowOperation: true });
        return parsed instanceof Operation ? unscaleParsedNumber(parsed, 100) : parsed;
    }

    /**
     * @param {boolean} _humanReadable
     * @returns {string}
     */
    formatValue(_humanReadable) {
        return formatPercentage(this.value, {
            digits: this.props.digits,
            trailingZeros: this.props.trailingZeros,
            noSymbol: true,
            field: this.field.definition,
        });
    }

    /** @returns {string} */
    get formattedValueWithSymbol() {
        return formatPercentage(this.value, {
            digits: this.props.digits,
            trailingZeros: this.props.trailingZeros,
            field: this.field.definition,
        });
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
const percentageField = {
    component: PercentageField,
    displayName: _t("Percentage"),
    supportedOptions: [
        {
            label: _t("Digits"),
            name: "digits",
            type: "digits",
        },
        { ...hideTrailingZerosOption(), default: true },
    ],
    supportedAttributes: [digitsAttribute()],
    supportedTypes: ["float"],
    isEmpty: isFalseEmpty,
    extractProps: ({ attrs, options }) => ({
        digits: extractDigits({ attrs, options }),
        trailingZeros: extractPercentageTrailingZeros(options),
    }),
};

registerField("percentage", percentageField);
