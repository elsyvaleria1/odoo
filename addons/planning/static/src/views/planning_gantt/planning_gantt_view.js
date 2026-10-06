/** @odoo-module native */
import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";

import { PlanningSearchModel } from "../planning_search_model.js";
import { PlanningGanttController } from "./planning_gantt_controller.js";
import { PlanningGanttModel } from "./planning_gantt_model.js";
import { PlanningGanttRenderer } from "./planning_gantt_renderer.js";

const viewRegistry = registry.category("views");

export const planningGanttView = {
    ...ganttView,
    SearchModel: PlanningSearchModel,
    Controller: PlanningGanttController,
    Renderer: PlanningGanttRenderer,
    Model: PlanningGanttModel,
    buttonTemplate: "planning.PlanningGanttView.Buttons",
};

viewRegistry.add("planning_gantt", planningGanttView);
