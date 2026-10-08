/** @odoo-module native */
import { onWillUpdateProps, proxy, t } from "@odoo/owl";
import { useAppContext } from "@web/core/app_context";
import { _t } from "@web/core/translation";
import { clearUncommittedChanges } from "@web/webclient/actions";

import { TemplateDropdown } from "./template_dropdown.js";

export class ProjectTaskTemplateDropdown extends TemplateDropdown {
    static props = {
        ...TemplateDropdown.props,
        projectId: t.or([t.number(), t.boolean(), t.literal(null)]).optional(null),
    };

    setup() {
        super.setup();
        this.appContext = useAppContext();
        // industry_fsm's patch fills this key
        this.state = proxy({ taskTemplates: [] });
        onWillUpdateProps(this.onWillUpdateProps);
    }

    get templates() {
        return this.state.taskTemplates;
    }

    get templateResModel() {
        return "project.task";
    }

    get templateItemClass() {
        return "o-task-template";
    }

    get newRecordLabel() {
        return _t("New Task");
    }

    get templatesHeader() {
        return _t("Task Templates");
    }

    async onWillUpdateProps(nextProps) {
        if (nextProps.projectId !== this.props.projectId) {
            await this.fetchTemplates(nextProps);
        }
    }

    async fetchTemplates({ projectId }) {
        if (!projectId) {
            this.state.taskTemplates = [];
            return;
        }
        this.state.taskTemplates = await this.cachedOrm((templates) => {
            if (this.props.projectId === projectId) {
                this.state.taskTemplates = templates;
            }
        }).call("project.project", "get_template_tasks", [projectId]);
    }

    async createFromTemplate({ id: templateId }) {
        const context = this.getCreateContext();
        if (!(await clearUncommittedChanges(this.appContext))) {
            return;
        }
        const resId = await this.orm.call(
            "project.task",
            "action_create_from_template",
            [templateId],
            { context },
        );
        await this.action.switchView("form", { resId, focusTitle: true });
    }
}
