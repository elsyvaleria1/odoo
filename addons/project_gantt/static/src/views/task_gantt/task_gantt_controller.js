/** @odoo-module native */
import { ProjectTaskTemplateDropdown } from "@project/views/components/project_task_template_dropdown";
import { GanttController } from "@web_gantt/gantt_controller";

export class TaskGanttController extends GanttController {
    static template = "project_gantt.TaskGanttController";
    static components = {
        ...GanttController.components,
        ProjectTaskTemplateDropdown,
    };
}
