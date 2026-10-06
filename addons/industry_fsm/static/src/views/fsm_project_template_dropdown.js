/** @odoo-module native */
import { ProjectTemplateDropdown } from "@project/views/components/project_template_dropdown";
import { patch } from "@web/core/utils/patch";

patch(ProjectTemplateDropdown.prototype, {
    /**
     * @override
     */
    get projectTemplatesDomain() {
        const parentDomain = super.projectTemplatesDomain;
        if (this.props.context.fsm_mode) {
            return [...parentDomain, ["is_fsm", "=", true]];
        }
        return parentDomain;
    },
});
