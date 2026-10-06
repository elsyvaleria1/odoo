/** @odoo-module native */
import { ProjectTaskControlPanel } from "@project/views/project_task_control_panel/project_task_control_panel";
import { TaskGanttArchParserCommon } from "@project_gantt/views/project_task_common/task_gantt_arch_parser_common";
import { TaskGanttModelCommon } from "@project_gantt/views/project_task_common/task_gantt_model_common";
import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";

import { TaskSharingGanttController } from "./task_sharing_gantt_controller.js";
import { TaskSharingGanttRenderer } from "./task_sharing_gantt_renderer.js";

const viewRegistry = registry.category("views");

export const taskSharingGanttView = {
    ...ganttView,
    Controller: TaskSharingGanttController,
    ControlPanel: ProjectTaskControlPanel,
    ArchParser: TaskGanttArchParserCommon,
    Model: TaskGanttModelCommon,
    Renderer: TaskSharingGanttRenderer,
};

viewRegistry.add("task_sharing_gantt", taskSharingGanttView);
