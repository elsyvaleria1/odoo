/** @odoo-module native */
import { t } from "@odoo/owl";
import { now, toLocaleString } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import {
    SelectionField,
    selectionField,
} from "@web/fields/selection/selection/selection_field";

/** @param {Temporal.ZonedDateTime} value */
function monthLong(value) {
    return toLocaleString(value, { month: "long" });
}

/** @param {Temporal.ZonedDateTime} value */
function monthShort(value) {
    return toLocaleString(value, { month: "short" });
}

export class TimePeriodSelectionField extends SelectionField {
    static props = { ...SelectionField.props, onChange: t.function().optional() };

    onChange(ev) {
        super.onChange(ev);
        if (this.props.onChange) {
            this.props.onChange(ev);
        }
    }

    get options() {
        const date1 = now().with({ day: 1 }).subtract({ years: 1 });
        const date2 = date1.add({ months: 1 });
        const date3 = date1.add({ months: 2 });
        const options = [];
        for (const option of this.props.record.fields[this.props.name].selection) {
            if (option[0] === "last_year") {
                options.push([option[0], `${monthLong(date1)} ${date1.year}`]);
            } else if (option[0] === "last_year_m_plus_1") {
                options.push([option[0], `${monthLong(date2)} ${date2.year}`]);
            } else if (option[0] === "last_year_m_plus_2") {
                options.push([option[0], `${monthLong(date3)} ${date3.year}`]);
            } else if (option[0] === "last_year_quarter") {
                let beginDate = monthShort(date1);
                const endDate = `${monthShort(date3)} ${date3.year}`;
                if (date1.year !== date3.year) {
                    beginDate += ` ${date1.year}`;
                }
                options.push([option[0], `${beginDate}-${endDate}`]);
            } else if (option[0] !== false && option[1] !== "") {
                options.push(option);
            }
        }
        return options;
    }
}

export const timePeriodSelectionField = {
    ...selectionField,
    component: TimePeriodSelectionField,
    displayName: _t("Time Perdiod Selection"),
    supportedTypes: ["selection"],
};

registry.category("fields").add("time_period_selection", timePeriodSelectionField);
