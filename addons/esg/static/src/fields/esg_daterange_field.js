/** @odoo-module native */
import { registry } from "@web/core/registry";
import {
    dateField,
    DateTimeField,
    listDateField,
    ListDateTimeField,
} from "@web/fields/temporal/datetime";

export class EsgDateTimeField extends DateTimeField {
    static template = "esg.EsgDateTimeField";

    shouldShowSeparator() {
        return !this.isEmpty(this.endDateField) && super.shouldShowSeparator();
    }
}

export const esgDateRangeField = {
    ...dateField,
    component: EsgDateTimeField,
};

registry.category("fields").add("esg_daterange", esgDateRangeField);

export class EsgListDateTimeField extends ListDateTimeField {
    static template = "esg.EsgDateTimeField";

    shouldShowSeparator() {
        return !this.isEmpty(this.endDateField) && super.shouldShowSeparator();
    }
}

export const esgListDateRangeField = {
    ...listDateField,
    component: EsgListDateTimeField,
};

registry.category("fields").add("esg_list_daterange", esgListDateRangeField);
