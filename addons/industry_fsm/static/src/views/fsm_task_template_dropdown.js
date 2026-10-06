/** @odoo-module native */
import { ProjectTaskTemplateDropdown } from "@project/views/components/project_task_template_dropdown";
import { patch } from "@web/core/utils/patch";

patch(ProjectTaskTemplateDropdown.prototype, {
    /**
     * @override
     */
    async onWillStart() {
        await Promise.all([
            super.onWillStart(),
            !this.props.projectId &&
                this.props.context.fsm_mode &&
                this.fetchFsmTaskTemplates(),
        ]);
    },

    async fetchFsmTaskTemplates() {
        this.state.taskTemplates = await this.orm
            .cache({
                type: "disk",
                update: "always",
                callback: (result, hasChanged) => {
                    if (hasChanged) {
                        this.state.taskTemplates = result;
                    }
                },
            })
            .searchRead(
                "project.task",
                [
                    ["is_template", "=", true],
                    ["is_fsm", "=", true],
                ],
                ["id", "name"],
            );
    },
});
