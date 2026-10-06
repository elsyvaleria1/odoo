/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { EsgCarbonEmissionKanbanController } from "./esg_carbon_emission_kanban_controller.js";

export const EsgCarbonEmissionKanbanView = {
    ...kanbanView,
    Controller: EsgCarbonEmissionKanbanController,
};

registry
    .category("views")
    .add("esg_carbon_emission_kanban", EsgCarbonEmissionKanbanView);
