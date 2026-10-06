/** @odoo-module native */
import { registry } from "@web/core/registry";
import { pivotView } from "@web/views/pivot";

import { EsgCarbonEmissionPivotController } from "./esg_carbon_emission_pivot_controller.js";

export const EsgCarbonEmissionPivotView = {
    ...pivotView,
    Controller: EsgCarbonEmissionPivotController,
};

registry.category("views").add("esg_carbon_emission_pivot", EsgCarbonEmissionPivotView);
