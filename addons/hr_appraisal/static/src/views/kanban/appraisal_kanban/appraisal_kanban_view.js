/** @odoo-module native */
import { AppraisalActionHelper } from "@hr_appraisal/views/helper/appraisal_helper_view/appraisal_helper_view";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { KanbanRenderer, kanbanView } from "@web/views/kanban";

export class AppraisalKanbanRenderer extends KanbanRenderer {
    static template = "hr_appraisal.AppraisalKanbanRenderer";
    static components = {
        ...KanbanRenderer.components,
        AppraisalActionHelper,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}

export const AppraisalKanbanView = {
    ...kanbanView,
    Renderer: AppraisalKanbanRenderer,
};

registry.category("views").add("appraisal_kanban_view", AppraisalKanbanView);
