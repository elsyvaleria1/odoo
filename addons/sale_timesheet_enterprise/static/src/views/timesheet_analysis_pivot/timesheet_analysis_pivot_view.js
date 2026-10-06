/** @odoo-module native */
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot";

import { TimesheetAnalysisPivotModel } from "./timesheet_analysis_pivot_model.js";

const viewRegistry = registry.category("views");

export const timesheetAnalysysPivotView = {
    ...pivotView,
    Model: TimesheetAnalysisPivotModel,
};

viewRegistry.add("timesheet_analysis_pivot_view", timesheetAnalysysPivotView);
