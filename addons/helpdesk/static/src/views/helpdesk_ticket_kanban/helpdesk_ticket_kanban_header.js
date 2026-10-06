/** @odoo-module native */
import { RottingKanbanHeader } from "@mail/views/web/rotting/rotting_kanban_header";

import { HelpdeskTicketGroupConfigMenu } from "../helpdesk_ticket_group_config_menu.js";

export class HelpdeskTicketKanbanHeader extends RottingKanbanHeader {
    static components = {
        ...RottingKanbanHeader.components,
        GroupConfigMenu: HelpdeskTicketGroupConfigMenu,
    };
}
