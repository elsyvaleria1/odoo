/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { PosKanbanController } from "./kanban_controller.js";
import { PosKanbanRenderer } from "./kanban_renderer.js";

export const posKanbanView = {
    ...kanbanView,
    Renderer: PosKanbanRenderer,
    Controller: PosKanbanController,
};

registry.category("views").add("pos_kanban", posKanbanView);
