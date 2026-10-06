/** @odoo-module native */
import { projectTaskCalendarView } from "@project/views/project_task_calendar/project_task_calendar_view";
import { registry } from "@web/core/registry";

import { FsmTaskCalendarModel } from "./fsm_calendar_model.js";

export const fsmTaskCalendarView = {
    ...projectTaskCalendarView,
    Model: FsmTaskCalendarModel,
};

registry.category("views").add("fsm_task_calendar", fsmTaskCalendarView);
