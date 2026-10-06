/** @odoo-module native */
import { t } from "@odoo/owl";
import { GanttRowProgressBar } from "@web_gantt/gantt_row_progress_bar";

export class PlanningGanttRowProgressBar extends GanttRowProgressBar {
    static template = "planning.PlanningGanttRowProgressBar";
    static props = {
        ...GanttRowProgressBar.props,
        progressBar: t.object({
            ...GanttRowProgressBar.props.progressBar.toShape(),
            is_flexible_hours: t.boolean().optional(),
            is_fully_flexible_hours: t.boolean().optional(),
        }),
    };
}
