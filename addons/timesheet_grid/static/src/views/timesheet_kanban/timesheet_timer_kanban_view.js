/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { TimesheetTimerKanbanController } from "./timesheet_timer_kanban_controller.js";
import { TimesheetTimerKanbanRenderer } from "./timesheet_timer_kanban_renderer.js";

class TimesheetTimerKanbanModel extends kanbanView.Model {
    static withCache = false;
}

export const timesheetTimerKanbanView = {
    ...kanbanView,
    Controller: TimesheetTimerKanbanController,
    Model: TimesheetTimerKanbanModel,
    Renderer: TimesheetTimerKanbanRenderer,
};

registry.category("views").add("timesheet_timer_kanban", timesheetTimerKanbanView);
