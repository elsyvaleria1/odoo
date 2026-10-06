/** @odoo-module native */
import { registry } from "@web/core/registry";

import { timesheetGridView } from "../timesheet_grid/timesheet_grid_view.js";
import { TimerTimesheetGridController } from "./timer_timesheet_grid_controller.js";
import { TimerTimesheetGridModel } from "./timer_timesheet_grid_model.js";
import { TimerTimesheetGridRenderer } from "./timer_timesheet_grid_renderer.js";

export const timerTimesheetGridView = {
    ...timesheetGridView,
    Controller: TimerTimesheetGridController,
    Model: TimerTimesheetGridModel,
    Renderer: TimerTimesheetGridRenderer,
};

registry.category("views").add("timer_timesheet_grid", timerTimesheetGridView);
