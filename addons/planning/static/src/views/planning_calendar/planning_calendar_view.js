/** @odoo-module native */
import { registry } from "@web/core/registry";
import { calendarView } from "@web/views/calendar";

import { PlanningSearchModel } from "../planning_search_model.js";
import { PlanningCalendarController } from "./planning_calendar_controller.js";
import { PlanningCalendarModel } from "./planning_calendar_model.js";
import { PlanningCalendarRenderer } from "./planning_calendar_renderer.js";

export const planningCalendarView = {
    ...calendarView,
    SearchModel: PlanningSearchModel,
    Model: PlanningCalendarModel,
    Controller: PlanningCalendarController,
    Renderer: PlanningCalendarRenderer,
    buttonTemplate: "planning.PlanningCalendarController.controlButtons",
};
registry.category("views").add("planning_calendar", planningCalendarView);
