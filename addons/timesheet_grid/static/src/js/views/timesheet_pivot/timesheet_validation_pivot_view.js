/** @odoo-module native */
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot";

import { TimesheetValidationPivotRenderer } from "./timesheet_validation_pivot_renderer.js";

export const TimesheetValidationPivotView = {
    ...pivotView,
    Renderer: TimesheetValidationPivotRenderer,
    buttonTemplate: "timesheet_grid.TimesheetValidationPivotView.Buttons",
};

registry
    .category("views")
    .add("timesheet_validation_pivot_view", TimesheetValidationPivotView);
