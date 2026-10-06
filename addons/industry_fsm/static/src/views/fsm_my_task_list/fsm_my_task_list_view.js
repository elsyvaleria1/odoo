/** @odoo-module native */
import { projectTaskListView } from "@project/views/project_task_list/project_task_list_view";
import { registry } from "@web/core/registry";

import { FsmMyTaskListController } from "./fsm_my_task_list_controller.js";

export const fsmMyTaskListView = {
    ...projectTaskListView,
    Controller: FsmMyTaskListController,
};

registry.category("views").add("fsm_my_task_list", fsmMyTaskListView);
