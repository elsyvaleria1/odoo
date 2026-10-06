/** @odoo-module native */
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot";

import { PlanningSearchModel } from "../planning_search_model.js";
import { PlanningPivotModel } from "./planning_pivot_model.js";

registry.category("views").add("planning_pivot", {
    ...pivotView,
    SearchModel: PlanningSearchModel,
    Model: PlanningPivotModel,
});
