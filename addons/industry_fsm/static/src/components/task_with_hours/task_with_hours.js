/** @odoo-module native */
import { TaskWithHours } from "@hr_timesheet/components/task_with_hours/task_with_hours";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { buildM2OFieldDescription } from "@web/fields/relational/many2one";

patch(TaskWithHours.prototype, {
    setup() {
        this.createEditProjectIdsService = useService("create_edit_project_ids");
        super.setup();
    },

    get m2oProps() {
        const m2oProps = super.m2oProps;
        const projectIds = this.createEditProjectIdsService.projectIds;
        if (projectIds !== undefined && m2oProps.canCreate) {
            m2oProps.canQuickCreate =
                m2oProps.canQuickCreate &&
                !projectIds.includes(this.props.record.data.project_id.id);
        }
        return m2oProps;
    },
});

export class FsmTaskWithHours extends TaskWithHours {
    async onWillStart() {
        await Promise.all([
            super.onWillStart(),
            this.createEditProjectIdsService.fetchProjectIds(),
        ]);
    }
}

registry
    .category("fields")
    .add(
        "task_with_hours",
        { ...buildM2OFieldDescription(FsmTaskWithHours) },
        { force: true },
    )
    .add("list.task_with_hours", { ...buildM2OFieldDescription(TaskWithHours) });
