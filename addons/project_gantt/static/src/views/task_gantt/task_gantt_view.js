/** @odoo-module native */
import { ProjectTaskControlPanel } from "@project/views/project_task_control_panel/project_task_control_panel";
import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";

import { TaskGanttArchParser } from "./task_gantt_arch_parser.js";
import { TaskGanttController } from "./task_gantt_controller.js";
import { TaskGanttModel } from "./task_gantt_model.js";
import { TaskGanttRenderer } from "./task_gantt_renderer.js";

const viewRegistry = registry.category("views");

export const taskGanttView = {
    ...ganttView,
    ControlPanel: ProjectTaskControlPanel,
    Controller: TaskGanttController,
    ArchParser: TaskGanttArchParser,
    Model: TaskGanttModel,
    Renderer: TaskGanttRenderer,
};

viewRegistry.add("task_gantt", taskGanttView);
