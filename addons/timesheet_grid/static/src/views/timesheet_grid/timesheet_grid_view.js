/** @odoo-module native */
import { registry } from "@web/core/registry";
import { gridView } from "@web_grid/views/grid_view";

import { TimesheetGridController } from "./timesheet_grid_controller.js";
import { TimesheetGridModel } from "./timesheet_grid_model.js";
import { TimesheetGridRenderer } from "./timesheet_grid_renderer.js";
import { TimesheetGridSearchModel } from "./timesheet_grid_search_model.js";

export const timesheetGridView = {
    ...gridView,
    Controller: TimesheetGridController,
    Model: TimesheetGridModel,
    Renderer: TimesheetGridRenderer,
    SearchModel: TimesheetGridSearchModel,
};

registry.category("views").add("timesheet_grid", timesheetGridView);
