/** @odoo-module native */
import { GraphRenderer } from "@web/views/graph";

import { HelpdeskTicketAnalysisRendererMixin } from "../helpdesk_ticket_analysis_renderer_mixin.js";

export class HelpdeskTicketAnalysisGraphRenderer extends HelpdeskTicketAnalysisRendererMixin(
    GraphRenderer,
) {}
