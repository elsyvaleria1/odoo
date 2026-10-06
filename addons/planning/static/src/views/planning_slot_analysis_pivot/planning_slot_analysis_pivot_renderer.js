/** @odoo-module native */
import { PivotRenderer } from "@web/views/pivot";

import { PlanningSlotAnalysisRendererMixin } from "../planning_slot_analysis_renderer_mixin.js";

export class PlanningSlotAnalysisPivotRenderer extends PlanningSlotAnalysisRendererMixin(
    PivotRenderer,
) {}
