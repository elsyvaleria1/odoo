/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban";

export class EsgCarbonEmissionKanbanController extends KanbanController {
    setup() {
        super.setup(...arguments);
        this.actionService = useService("action");
    }

    async createRecord() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "esg.other.emission",
            views: [[false, "form"]],
            target: "current",
        });
    }
}
