/** @odoo-module native */

import { registry } from "@web/core/registry";

import { timesheetGridView } from "../timesheet_grid/timesheet_grid_view.js";
import { TimesheetToValidateGridModel } from "./timesheet_to_validate_grid_model.js";

export const timesheetToValidateGridView = {
    ...timesheetGridView,
    Model: TimesheetToValidateGridModel,
};

registry
    .category("views")
    .add("timesheet_to_validate_grid", timesheetToValidateGridView);
