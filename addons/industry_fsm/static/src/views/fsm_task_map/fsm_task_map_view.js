/** @odoo-module native */
import { projectTaskMapView } from "@project_map/views/project_task_map/project_task_map_view";
import { registry } from "@web/core/registry";

import { FsmTaskMapRenderer } from "./fsm_task_map_renderer.js";

export const fsmTaskMapView = {
    ...projectTaskMapView,
    Renderer: FsmTaskMapRenderer,
};

registry.category("views").add("fsm_task_map", fsmTaskMapView);
