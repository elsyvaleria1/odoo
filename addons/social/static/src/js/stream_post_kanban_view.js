/** @odoo-module native */
import { registry } from "@web/core/registry";
import { kanbanView } from "@web/views/kanban";

import { StreamPostKanbanController } from "./stream_post_kanban_controller.js";
import { StreamPostKanbanModel } from "./stream_post_kanban_model.js";
import { StreamPostKanbanRenderer } from "./stream_post_kanban_renderer.js";

export const StreamPostKanbanView = {
    ...kanbanView,
    Controller: StreamPostKanbanController,
    Model: StreamPostKanbanModel,
    Renderer: StreamPostKanbanRenderer,
    buttonTemplate: "StreamPostKanbanView.buttons",
};

registry.category("views").add("social_stream_post_kanban_view", StreamPostKanbanView);
