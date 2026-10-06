/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { PlanningRelationalModel } from "../planning_relational_model.js";
import { PlanningSearchModel } from "../planning_search_model.js";
import { PlanningKanbanController } from "./planning_kanban_controller.js";

registry.category("views").add("planning_kanban", {
    ...kanbanView,
    Controller: PlanningKanbanController,
    SearchModel: PlanningSearchModel,
    Model: PlanningRelationalModel,
});
