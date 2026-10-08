/** @odoo-module native */
import { KanbanController } from "@web/views/kanban";

import { ProjectUpdateControllerMixin } from "../project_update_controller_mixin.js";

export class ProjectUpdateKanbanController extends ProjectUpdateControllerMixin(
    KanbanController,
) {
    static template = "project.ProjectUpdateKanbanView";
}
