/** @odoo-module native */
import { GraphRenderer } from "@web/views/graph";

import { PlanningSlotAnalysisRendererMixin } from "../planning_slot_analysis_renderer_mixin.js";

export class PlanningSlotAnalysisGraphRenderer extends PlanningSlotAnalysisRendererMixin(
    GraphRenderer,
) {}
