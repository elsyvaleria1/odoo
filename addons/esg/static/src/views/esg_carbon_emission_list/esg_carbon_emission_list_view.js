/** @odoo-module native */
import { registry } from "@web/core/registry";
import { listView } from "@web/views/list";

import { EsgCarbonEmissionListController } from "./esg_carbon_emission_list_controller.js";
import { EsgCarbonEmissionListRenderer } from "./esg_carbon_emission_list_renderer.js";

export const EsgCarbonEmissionListView = {
    ...listView,
    Controller: EsgCarbonEmissionListController,
    Renderer: EsgCarbonEmissionListRenderer,
};

registry.category("views").add("esg_carbon_emission_list", EsgCarbonEmissionListView);
