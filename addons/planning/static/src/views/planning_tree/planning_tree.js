/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { PlanningRelationalModel } from "../planning_relational_model.js";
import { PlanningSearchModel } from "../planning_search_model.js";
import { PlanningTreeController } from "./planning_tree_controller.js";

registry.category("views").add("planning_tree", {
    ...listView,
    Controller: PlanningTreeController,
    SearchModel: PlanningSearchModel,
    Model: PlanningRelationalModel,
});
