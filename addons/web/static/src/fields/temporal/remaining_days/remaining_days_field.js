// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { formatFieldDate } from "@web/core/formatters";
import { diff, toDate, today, toRelativeCalendar } from "@web/core/l10n/dates";
import { evaluateExpr } from "@web/core/py_js/py";
import { _t } from "@web/core/translation";
import { getClassNameFromDecoration } from "@web/core/utils/decorations";
import { capitalize } from "@web/core/utils/format/strings";
import { registerField } from "@web/fields/_registry";
import { FieldComponent } from "@web/fields/field_component";
import { standardFieldProps } from "@web/fields/standard_field_props";
import { DateTimeField } from "@web/fields/temporal/datetime/datetime_field";

export class RemainingDaysField extends FieldComponent {
    static components = { DateTimeField };

    static props = {
        ...standardFieldProps,
        classes: t.object().optional({
            bf: "days <= 0",
            danger: "days < 0",
            warning: "days == 0",
        }),
    };

    static template = "web.RemainingDaysField";

    /** @returns {number|null} */
    computeDiffDays() {
        const value = this.field.value;
        if (!value) {
            return null;
        }
        return Math.floor(diff(toDate(value), today(), "days"));
    }

    /** @returns {number|null} */
    get diffDays() {
        return this.computeDiffDays();
    }

    /** @returns {string} */
    get diffString() {
        const diffDays = this.diffDays;
        if (diffDays === null) {
            return "";
        }
        if (Math.abs(diffDays) > 99) {
            return this.formattedValue;
        }
        const value = this.field.value;
        return capitalize(
            toRelativeCalendar(value, Math.abs(diffDays) <= 30 ? "days" : undefined),
        );
    }

    /** @returns {string} */
    get formattedValue() {
        return formatFieldDate(this.field.value);
    }

    /** @returns {string} */
    get numericValue() {
        return formatFieldDate(this.field.value, { numeric: true });
    }

    /** @returns {Object|null} */
    get classNames() {
        if (this.diffDays === null) {
            return null;
        }
        if (!this.props.record.isActive) {
            return null;
        }
        const classNames = {};
        const evalContext = {
            days: this.diffDays,
            record: this.props.record.evalContext,
        };
        for (const decoration of Object.keys(this.props.classes)) {
            const value = evaluateExpr(this.props.classes[decoration], evalContext);
            /** @type {Record<string, any>} */ (classNames)[
                getClassNameFromDecoration(decoration)
            ] = value;
        }
        return classNames;
    }

    /** @returns {Object} */
    get dateTimeFieldProps() {
        return Object.fromEntries(
            Object.entries(this.props).filter(
                ([key]) => /** @type {Record<string, any>} */ (standardFieldProps)[key],
            ),
        );
    }
}

/** @type {import("registries").FieldsRegistryItemShape} */
const remainingDaysField = {
    component: RemainingDaysField,
    displayName: _t("Remaining Days"),
    supportedOptions: [
        {
            label: _t("Decoration expressions"),
            name: "classes",
            type: "string",
            help: _t(
                "Map of decoration name to a python expression over `days`, e.g. {'danger': 'days < 0'}.",
            ),
        },
    ],
    supportedTypes: ["date", "datetime"],
    extractProps: ({ options }) => ({
        classes: options.classes,
    }),
};

registerField("remaining_days", remainingDaysField);
