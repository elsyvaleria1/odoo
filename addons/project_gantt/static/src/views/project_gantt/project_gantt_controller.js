/** @odoo-module native */
import { ProjectTemplateDropdown } from "@project/views/components/project_template_dropdown";
import { GanttController } from "@web_gantt/gantt_controller";

export class ProjectGanttController extends GanttController {
    static template = "project_gantt.ProjectGanttController";
    static components = {
        ...GanttController.components,
        ProjectTemplateDropdown,
    };
}
