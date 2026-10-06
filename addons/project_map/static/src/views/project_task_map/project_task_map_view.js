/** @odoo-module native */
import { HighlightProjectTaskSearchModel } from "@project/views/highlight_project_task_search_model";
import { ProjectTaskControlPanel } from "@project/views/project_task_control_panel/project_task_control_panel";
import { registry } from "@web/core/registry";
import { mapView } from "@web_map/map_view/map_view";

import { ProjectTaskMapModel } from "./project_task_map_model.js";
import { ProjectTaskMapRenderer } from "./project_task_map_renderer.js";

export const projectTaskMapView = {
    ...mapView,
    ControlPanel: ProjectTaskControlPanel,
    Model: ProjectTaskMapModel,
    Renderer: ProjectTaskMapRenderer,
    SearchModel: HighlightProjectTaskSearchModel,
};

registry.category("views").add("project_task_map", projectTaskMapView);
