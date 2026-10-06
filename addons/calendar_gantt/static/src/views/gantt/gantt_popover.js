/** @odoo-module native */
import { t } from "@odoo/owl";
import { GanttPopover } from "@web_gantt/gantt_popover";

export class AppointmentGanttPopover extends GanttPopover {
    static template = "calendar.booking.GanttPopover";
    static props = { ...GanttPopover.props, headerClass: t.string().optional() };
    setup() {
        super.setup();
        this.displayPopoverHeader = true;
    }
}
