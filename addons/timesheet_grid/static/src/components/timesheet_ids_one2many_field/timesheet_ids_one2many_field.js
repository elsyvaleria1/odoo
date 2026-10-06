/** @odoo-module native */
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";

import { TimesheetsListRenderer } from "./timesheets_list_renderer.js";

export class TimesheetIdsOne2ManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: TimesheetsListRenderer,
    };
}

export const timesheetIdsOne2ManyField = {
    ...x2ManyField,
    component: TimesheetIdsOne2ManyField,
};

registry.category("fields").add("timesheets_one2many", timesheetIdsOne2ManyField);
