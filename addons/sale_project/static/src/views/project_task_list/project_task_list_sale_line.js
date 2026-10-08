/** @odoo-module native */
import { ProjectTaskListRenderer } from "@project/views/project_task_list/project_task_list_renderer";
import { patch } from "@web/core/utils/patch";

patch(ProjectTaskListRenderer.prototype, {
    isCellReadonly(column, record) {
        let readonly = false;
        if (column.name === "sale_line_id") {
            readonly = !this.haveAllSelectedSameField("partner_id");
        }
        return readonly || super.isCellReadonly(column, record);
    },
});
