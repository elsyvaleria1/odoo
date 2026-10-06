/** @odoo-module native */
import { PivotRenderer } from "@web/views/pivot";

import { HelpdeskTicketAnalysisRendererMixin } from "../helpdesk_ticket_analysis_renderer_mixin.js";

export class HelpdeskTicketAnalysisPivotRenderer extends HelpdeskTicketAnalysisRendererMixin(
    PivotRenderer,
) {}
