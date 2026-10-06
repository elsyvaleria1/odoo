/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { dateSettings } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useInputField } from "@web/fields/input_field_hook";
import { useNumpadDecimal } from "@web/fields/numpad_decimal_hook";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class DurationField extends Component {
    static template = "pos_enterprise.DurationField";
    static props = { ...standardFieldProps, inputType: t.string().optional("text") };
    props = useProps(this.constructor.props);

    setup() {
        this.numpadDecimalRef = elementRef();
        this.inputRef = useInputField({
            getValue: () => this.displayValue,
            ref: this.numpadDecimalRef,
        });
        useNumpadDecimal(this.numpadDecimalRef);
    }

    get displayValue() {
        const value = this.props.record.data[this.props.name];
        return formatDuration(value);
    }
}

export const durationField = {
    component: DurationField,
    displayName: _t("Duration"),
    supportedTypes: ["float", "integer"],
    isEmpty: () => false,
    extractProps: ({ options }) => ({
        inputType: options?.type || "text",
    }),
};

function formatDuration(value) {
    if (value === undefined || value === null || isNaN(value) || value < 0) {
        return "";
    }
    const number = new Intl.NumberFormat(dateSettings.locale, {
        numberingSystem: dateSettings.numberingSystem,
        useGrouping: false,
        maximumFractionDigits: 3,
    });
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    const seconds = value % 60;
    const formatted =
        `${number.format(days)}d ${number.format(hours)}h ` +
        `${number.format(minutes)}m ${number.format(seconds)}s`;
    return formatted.replace(/\b0[dhms]\b\s*/g, "").trim();
}

registry.category("fields").add("duration_time", durationField);
registry.category("formatters").add("duration_time", formatDuration);
