/** @odoo-module native */
import { ListController } from "@web/views/list";

import { ProjectTemplateDropdown } from "../components/project_template_dropdown.js";
import { ProjectManagerActionsMixin } from "../project_manager_actions_mixin.js";

export class ProjectListController extends ProjectManagerActionsMixin(ListController) {
    static template = "project.ProjectListView";
    static components = {
        ...ListController.components,
        ProjectTemplateDropdown,
    };
}
