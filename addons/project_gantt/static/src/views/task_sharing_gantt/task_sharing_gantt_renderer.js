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

    /**
     * Determines whether the task should allow Resize/Drag based on the following conditions:
     * 1. The task is not grouped exclusively by 'step_id' or 'tag_ids'.
     * 2. The task depends on other tasks (predecessor_ids is not empty).
     * 3. Other tasks depend on this task (dependent_tasks_count is truthy).
     */
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

    /**
     *
     * The connector line highlight and display buttons will be hidden.
     */
    toggleConnectorHighlighting() {
        return;
    }
}
