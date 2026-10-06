/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { TimesheetTimerListController } from "./timesheet_timer_list_controller.js";
import { TimesheetTimerListRenderer } from "./timesheet_timer_list_renderer.js";

class TimesheetTimerListModel extends listView.Model {
    static withCache = false;
}

export const timesheetTimerListView = {
    ...listView,
    Controller: TimesheetTimerListController,
    Model: TimesheetTimerListModel,
    Renderer: TimesheetTimerListRenderer,
};

registry.category("views").add("timesheet_timer_list", timesheetTimerListView);
