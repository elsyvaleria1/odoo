/** @odoo-module native */
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot";

import { PlanningSlotAnalysisPivotRenderer } from "./planning_slot_analysis_pivot_renderer.js";

registry.category("views").add("planning_slot_analysis_pivot", {
    ...pivotView,
    Renderer: PlanningSlotAnalysisPivotRenderer,
});
