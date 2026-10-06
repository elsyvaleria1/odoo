/** @odoo-module native */
import { t } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    Many2OneGridRow,
    many2OneGridRow,
} from "@web_grid/components/many2one_grid_row/many2one_grid_row";

import { useTimesheetOvertimeProps } from "../../hooks/useTimesheetOvertimeProps.js";
import { TimesheetOvertimeIndication } from "../timesheet_overtime_indication/timesheet_overtime_indication.js";

export class TimesheetGridMany2OneGridRow extends Many2OneGridRow {
    static template = "timesheet_grid.TimesheetGridMany2OneGridRow";

    static components = {
        ...Many2OneGridRow.components,
        TimesheetOvertimeIndication,
    };

    static props = { ...Many2OneGridRow.props, workingHours: t.object().optional() };

    setup() {
        super.setup(...arguments);
        this.timesheetOvertimeProps = useTimesheetOvertimeProps(this);
    }

    get overtimeProps() {
        return {
            ...this.timesheetOvertimeProps.props,
            name: this.props.name,
        };
    }
}

export const timesheetGridMany2OneGridRow = {
    ...many2OneGridRow,
    component: TimesheetGridMany2OneGridRow,
};

registry
    .category("grid_components")
    .add("timesheet_many2one", timesheetGridMany2OneGridRow);
