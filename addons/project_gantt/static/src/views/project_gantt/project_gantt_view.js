/** @odoo-module native */
import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";

import { ProjectGanttController } from "./project_gantt_controller.js";
import { ProjectGanttModel } from "./project_gantt_model.js";
import { ProjectGanttRenderer } from "./project_gantt_renderer.js";

export const projectGanttView = {
    ...ganttView,
    Controller: ProjectGanttController,
    Renderer: ProjectGanttRenderer,
    Model: ProjectGanttModel,
};

registry.category("views").add("project_gantt", projectGanttView);
