/** @odoo-module native */
import { registry } from "@web/core/registry";
import { graphView } from "@web/views/graph";

import { PlanningSearchModel } from "../planning_search_model.js";
import { PlanningGraphModel } from "./planning_graph_model.js";

registry.category("views").add("planning_graph", {
    ...graphView,
    SearchModel: PlanningSearchModel,
    Model: PlanningGraphModel,
});
