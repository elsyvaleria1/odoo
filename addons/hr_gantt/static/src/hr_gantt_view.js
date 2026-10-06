/** @odoo-module native */
import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";

import { HrGanttRenderer } from "./hr_gantt_renderer.js";

const viewRegistry = registry.category("views");

export const hrGanttView = {
    ...ganttView,
    Renderer: HrGanttRenderer,
};

viewRegistry.add("hr_gantt", hrGanttView);
