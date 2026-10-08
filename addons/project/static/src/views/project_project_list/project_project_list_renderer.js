/** @odoo-module native */
import { ListRenderer } from "@web/views/list";

import { ListSelectionSameFieldMixin } from "../list_selection_same_field_mixin.js";
import { ProjectProjectGroupConfigMenu } from "../project_project_kanban/project_project_group_config_menu.js";

export class ProjectProjectListRenderer extends ListSelectionSameFieldMixin(
    ListRenderer,
) {
    static components = {
        ...ListRenderer.components,
        GroupConfigMenu: ProjectProjectGroupConfigMenu,
    };

    isCellReadonly(column, record) {
        let readonly = super.isCellReadonly(column, record);
        if (!readonly && column.name === "phase_id") {
            readonly = !this.haveAllSelectedSameField("company_id");
        }
        return readonly;
    }
}
