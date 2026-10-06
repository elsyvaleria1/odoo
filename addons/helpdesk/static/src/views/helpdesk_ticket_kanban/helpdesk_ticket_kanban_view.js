/** @odoo-module native */
import { rottingKanbanView } from "@mail/views/web/rotting/rotting_kanban_view";
import { registry } from "@web/core/registry";

import { HelpdeskTicketRenderer } from "./helpdesk_ticket_kanban_renderer.js";

export const helpdeskTicketKanbanView = {
    ...rottingKanbanView,
    Renderer: HelpdeskTicketRenderer,
};

registry.category("views").add("helpdesk_ticket_kanban", helpdeskTicketKanbanView);
