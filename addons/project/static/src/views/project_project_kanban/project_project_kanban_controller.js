/** @odoo-module native */
import { KanbanController } from "@web/views/kanban";

import { ProjectTemplateDropdown } from "../components/project_template_dropdown.js";
import { ProjectManagerActionsMixin } from "../project_manager_actions_mixin.js";

export class ProjectKanbanController extends ProjectManagerActionsMixin(
    KanbanController,
) {
    static template = "project.ProjectKanbanView";
    static components = {
        ...KanbanController.components,
        ProjectTemplateDropdown,
    };
}
