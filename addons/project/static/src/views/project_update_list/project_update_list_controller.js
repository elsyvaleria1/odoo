/** @odoo-module native */
import { ListController } from "@web/views/list";

import { ProjectUpdateControllerMixin } from "../project_update_controller_mixin.js";

export class ProjectUpdateListController extends ProjectUpdateControllerMixin(
    ListController,
) {
    static template = "project.ProjectUpdateListView";
}
