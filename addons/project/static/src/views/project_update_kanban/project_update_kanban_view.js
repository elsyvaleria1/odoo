/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { ProjectUpdateKanbanController } from "./project_update_kanban_controller.js";

export const projectUpdateKanbanView = {
    ...kanbanView,
    Controller: ProjectUpdateKanbanController,
};

registry.category("views").add("project_update_kanban", projectUpdateKanbanView);
