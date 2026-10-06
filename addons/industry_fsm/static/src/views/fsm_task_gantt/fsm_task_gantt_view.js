/** @odoo-module native */
import { taskGanttView } from "@project_gantt/views/task_gantt/task_gantt_view";
import { registry } from "@web/core/registry";

import { FsmTaskGanttController } from "./fsm_task_gantt_controller.js";
import { FsmTaskGanttRenderer } from "./fsm_task_gantt_renderer.js";

export const fsmTaskGantt = {
    ...taskGanttView,
    Controller: FsmTaskGanttController,
    Renderer: FsmTaskGanttRenderer,
};

registry.category("views").add("fsm_task_gantt", fsmTaskGantt);
