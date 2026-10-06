/** @odoo-module native */
import { HelpdeskTeamDashboard } from "@helpdesk/components/helpdesk_team_dashboard/helpdesk_team_dashboard";
import { useService } from "@web/core/utils/hooks";
import { KanbanController } from "@web/views/kanban";

export class HelpdeskTeamKanbanController extends KanbanController {
    static template = "helpdesk.HelpdeskTeamKanbanView";
    static components = {
        ...KanbanController.components,
        HelpdeskTeamDashboard,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}
