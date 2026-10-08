/** @odoo-module native */
import { _t } from "@web/core/translation";

import { TemplateDropdown } from "./template_dropdown.js";

export class ProjectTemplateDropdown extends TemplateDropdown {
    get templateResModel() {
        return "project.project";
    }

    get templateItemClass() {
        return "o-project-template";
    }

    get newRecordLabel() {
        return _t("New Project");
    }

    get templatesHeader() {
        return _t("Project Templates");
    }

    get readFields() {
        return ["id", "name"];
    }

    get projectTemplatesDomain() {
        return [["is_template", "=", true]];
    }

    async fetchTemplates() {
        this.state.templates = await this.cachedOrm(
            (templates) => (this.state.templates = templates),
        ).searchRead("project.project", this.projectTemplatesDomain, this.readFields);
    }

    async createFromTemplate({ id: templateId, name: templateName }) {
        const action = await this.orm.call(
            "wizard.project.project.create.from.template",
            "action_view_template_view",
            [],
            {
                context: {
                    ...this.getCreateContext(),
                    template_id: templateId,
                    template_name: templateName,
                },
            },
        );
        this.action.doAction(action);
    }
}
