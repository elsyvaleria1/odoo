/** @odoo-module native */
import { ProjectTaskTemplateDropdown } from "@project/views/components/project_task_template_dropdown";
import { patch } from "@web/core/utils/patch";

patch(ProjectTaskTemplateDropdown.prototype, {
    /**
     * @override
     */
    async fetchTemplates(props) {
        if (props.projectId || !props.context.fsm_mode) {
            return super.fetchTemplates(props);
        }
        this.state.templates = await this.cachedOrm((templates) => {
            if (!this.props.projectId) {
                this.state.templates = templates;
            }
        }).searchRead(
            "project.task",
            [
                ["is_template", "=", true],
                ["is_fsm", "=", true],
            ],
            ["id", "name"],
        );
    },
});
