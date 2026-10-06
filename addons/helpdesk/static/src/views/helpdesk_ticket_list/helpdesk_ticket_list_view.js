/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { HelpdeskTicketListRenderer } from "./helpdesk_ticket_list_renderer.js";

export const helpdeskTicketListView = {
    ...listView,
    Renderer: HelpdeskTicketListRenderer,
};

registry.category("views").add("helpdesk_ticket_list", helpdeskTicketListView);
