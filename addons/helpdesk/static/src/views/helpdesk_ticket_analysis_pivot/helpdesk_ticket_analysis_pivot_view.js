/** @odoo-module native */
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot";

import { HelpdeskTicketAnalysisPivotRenderer } from "./helpdesk_ticket_analysis_pivot_renderer.js";

export const helpdeskTicketAnalysisPivotView = {
    ...pivotView,
    Renderer: HelpdeskTicketAnalysisPivotRenderer,
};

registry
    .category("views")
    .add("helpdesk_ticket_analysis_pivot", helpdeskTicketAnalysisPivotView);
