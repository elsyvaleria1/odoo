/** @odoo-module native */
import { registry } from "@web/core/registry";

import { fsmTaskMapView } from "../fsm_task_map/fsm_task_map_view.js";
import { FsmMyTaskMapController } from "./fsm_my_task_map_controller.js";

export const fsmMyTaskMapView = {
    ...fsmTaskMapView,
    Controller: FsmMyTaskMapController,
};

registry.category("views").add("fsm_my_task_map", fsmMyTaskMapView);
