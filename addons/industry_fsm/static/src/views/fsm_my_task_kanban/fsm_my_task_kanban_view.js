/** @odoo-module native */
import { projectTaskKanbanView } from "@project/views/project_task_kanban/project_task_kanban_view";
import { registry } from "@web/core/registry";

import { FsmMyTaskKanbanController } from "./fsm_my_task_kanban_controller.js";
import { FsmMyTaskKanbanRenderer } from "./fsm_my_task_kanban_renderer.js";

export const fsmMyTaskKanbanView = {
    ...projectTaskKanbanView,
    Controller: FsmMyTaskKanbanController,
    Renderer: FsmMyTaskKanbanRenderer,
};

registry.category("views").add("fsm_my_task_kanban", fsmMyTaskKanbanView);
