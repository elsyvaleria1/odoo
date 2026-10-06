/** @odoo-module native */
import { registry } from "@web/core/registry";
import { graphView } from "@web/views/graph";

import { PlanningSlotAnalysisGraphRenderer } from "./planning_slot_analysis_graph_renderer.js";

registry.category("views").add("planning_slot_analysis_graph", {
    ...graphView,
    Renderer: PlanningSlotAnalysisGraphRenderer,
});
