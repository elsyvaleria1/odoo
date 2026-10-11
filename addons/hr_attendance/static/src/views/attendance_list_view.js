/** @odoo-module native */
import { AttendanceActionHelper } from "@hr_attendance/views/attendance_helper_view";
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { ListRenderer, listView } from "@web/views/list";

export class AttendanceListRenderer extends ListRenderer {
    static template = "hr_attendance.AttendanceListRenderer";
    static components = {
        ...ListRenderer.components,
        AttendanceActionHelper,
    };

    setup() {
        super.setup();
        this.debug = useDebugMode();
    }

    get showNoContentHelper() {
        return super.showNoContentHelper && this.props.list.count < 6;
    }
}

export class AttendanceListModel extends listView.Model {
    async load(params = {}) {
        const domain = params.domain ?? this.config.domain ?? [];
        const filtersOnActive = domain.some(
            (condition) =>
                Array.isArray(condition) && condition[0] === "employee_id.active",
        );
        if (filtersOnActive) {
            return super.load(params);
        }
        return super.load({
            ...params,
            domain: [...domain, ["employee_id.active", "=", true]],
        });
    }
}

export const attendanceListView = {
    ...listView,
    Renderer: AttendanceListRenderer,
    Model: AttendanceListModel,
};

registry.category("views").add("attendance_list_view", attendanceListView);
