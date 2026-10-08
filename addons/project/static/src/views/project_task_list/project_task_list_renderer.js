/** @odoo-module native */
import { ListRenderer } from "@web/views/list";

import { ListSelectionSameFieldMixin } from "../list_selection_same_field_mixin.js";
import { ProjectTaskGroupConfigMenu } from "../project_task_kanban/project_task_group_config_menu.js";

export class ProjectTaskListRenderer extends ListSelectionSameFieldMixin(ListRenderer) {
    static components = {
        ...ListRenderer.components,
        GroupConfigMenu: ProjectTaskGroupConfigMenu,
    };

    isCellReadonly(column, record) {
        let readonly = false;
        if (column.name === "step_id") {
            readonly = !this.haveAllSelectedSameField("project_id");
        }
        return readonly || super.isCellReadonly(column, record);
    }
}
