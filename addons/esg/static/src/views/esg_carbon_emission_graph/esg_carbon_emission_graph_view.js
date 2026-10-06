/** @odoo-module native */
import { registry } from "@web/core/registry";
import { graphView } from "@web/views/graph";

import { EsgCarbonEmissionGraphController } from "./esg_carbon_emission_graph_controller.js";

export const EsgCarbonEmissionGraphView = {
    ...graphView,
    Controller: EsgCarbonEmissionGraphController,
};

registry.category("views").add("esg_carbon_emission_graph", EsgCarbonEmissionGraphView);
