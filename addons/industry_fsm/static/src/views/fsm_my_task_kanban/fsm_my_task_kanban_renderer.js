/** @odoo-module native */
import { ProjectTaskKanbanRenderer } from "@project/views/project_task_kanban/project_task_kanban_renderer";

import { FsmMyTaskKanbanRecord } from "./fsm_my_task_kanban_record.js";

export class FsmMyTaskKanbanRenderer extends ProjectTaskKanbanRenderer {
    static components = {
        ...ProjectTaskKanbanRenderer.components,
        KanbanRecord: FsmMyTaskKanbanRecord,
    };
}
