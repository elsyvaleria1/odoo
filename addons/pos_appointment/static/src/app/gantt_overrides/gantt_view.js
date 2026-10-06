/** @odoo-module native */
import { AppointmentBookingGanttView } from "@calendar_gantt/views/gantt/gantt_view";
import { POSAppointmentBookingGanttController } from "@pos_appointment/app/gantt_overrides/gantt_controller";
import { POSAppointmentBookingGanttRenderer } from "@pos_appointment/app/gantt_overrides/gantt_renderer";
import { registry } from "@web/core/registry";

export const posAppointmentBookingGanttView = {
    ...AppointmentBookingGanttView,
    Controller: POSAppointmentBookingGanttController,
    Renderer: POSAppointmentBookingGanttRenderer,
};

registry
    .category("views")
    .add("pos_appointment_booking_gantt", posAppointmentBookingGanttView);
