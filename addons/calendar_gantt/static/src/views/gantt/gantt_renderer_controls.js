/** @odoo-module native */
import { t } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { GanttRendererControls } from "@web_gantt/gantt_renderer_controls";

export class AppointmentBookingGanttRendererControls extends GanttRendererControls {
    static template = "calendar.booking.AppointmentBookingGanttRendererControls";
    static props = {
        ...GanttRendererControls.props,
        onClickAddLeave: t.any(),
        showAddLeaveButton: t.any(),
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}
