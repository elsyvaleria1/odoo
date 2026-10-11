/** @odoo-module native */
import { AttendanceActionHelper } from "@hr_attendance/views/attendance_helper_view";
import { onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { GanttController } from "@web_gantt/gantt_controller";
import { ganttView } from "@web_gantt/gantt_view";

import { AttendanceGanttModel } from "./attendance_gantt_model.js";
import { AttendanceGanttRenderer } from "./attendance_gantt_renderer.js";

export class HrAttendanceGanttController extends GanttController {
    static template = "hr_attendance.AttendanceGanttController";
    static components = {
        ...GanttController.components,
        AttendanceActionHelper,
    };
    /**
     * @override
     */
    setup() {
        super.setup();
        this.loadHelper = true;
        onMounted(() => {
            this.loadHelper = false;
        });
    }

    get showNoContentHelp() {
        return (
            this.model.data.rows.length < 2 &&
            this.model.data.rows[0].recordIds.length === 0
        );
    }
}
const viewRegistry = registry.category("views");

export const attendanceGanttView = {
    ...ganttView,
    Controller: HrAttendanceGanttController,
    Model: AttendanceGanttModel,
    Renderer: AttendanceGanttRenderer,
};

viewRegistry.add("attendance_gantt", attendanceGanttView);
