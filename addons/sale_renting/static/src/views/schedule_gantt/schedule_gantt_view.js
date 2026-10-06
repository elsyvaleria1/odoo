/** @odoo-module native */
import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";

import { ScheduleGanttModel } from "./schedule_gantt_model.js";
import { ScheduleGanttRenderer } from "./schedule_gantt_renderer.js";

export const scheduleGanttView = {
    ...ganttView,
    Model: ScheduleGanttModel,
    Renderer: ScheduleGanttRenderer,
};

registry.category("views").add("schedule_gantt", scheduleGanttView);
