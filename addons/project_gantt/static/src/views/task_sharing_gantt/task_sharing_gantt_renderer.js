/** @odoo-module native */
import { TaskGanttRendererCommon } from "@project_gantt/views/project_task_common/task_gantt_renderer_common";

import { TaskSharingGanttRendererControls } from "./task_sharing_gantt_renderer_controls.js";

export class TaskSharingGanttRenderer extends TaskGanttRendererCommon {
    static components = {
        ...TaskGanttRendererCommon.components,
        GanttRendererControls: TaskSharingGanttRendererControls,
    };
    static connectorCreatorTemplate =
        "project_gantt.TaskGanttRenderer.ConnectorCreator";

    onCellClicked() {
        return false;
    }

    disableResizeDrag(record) {
        const { groupBy } = this.model.searchParams;
        return (
            !groupBy.every((group) =>
                ["step_id", "tag_ids", "priority"].includes(group),
            ) ||
            record.predecessor_ids.length > 0 ||
            record.dependent_tasks_count
        );
    }

    getPill(record) {
        const pill = super.getPill(record);
        if (this.disableResizeDrag(record)) {
            pill.disableDrag = true;
        }

        return pill;
    }

    toggleConnectorHighlighting() {
        return;
    }
}
