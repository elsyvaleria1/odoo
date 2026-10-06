/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { HelpdeskTeamKanbanController } from "./helpdesk_team_kanban_controller.js";

export const HelpdeskTeamKanbanView = {
    ...kanbanView,
    Controller: HelpdeskTeamKanbanController,
};

registry.category("views").add("helpdesk_team_kanban_view", HelpdeskTeamKanbanView);
