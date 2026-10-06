/** @odoo-module native */
import { t } from "@odoo/owl";
import { GanttRowProgressBar } from "@web_gantt/gantt_row_progress_bar";

export class AttendanceGanttRowProgressBar extends GanttRowProgressBar {
    static template = "hr_attendance.AttendanceGanttRowProgressBar";
    static props = {
        ...GanttRowProgressBar.props,
        progressBar: t.object({
            ...GanttRowProgressBar.props.progressBar.toShape(),
            is_fully_flexible_hours: t.boolean().optional(),
        }),
    };

    get status() {
        const { max_value, value } = this.props.progressBar;
        if (value > max_value) {
            return "danger";
        } else {
            return "success";
        }
    }
}
