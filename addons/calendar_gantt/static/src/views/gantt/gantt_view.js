/** @odoo-module native */
import { AppointmentBookingGanttController } from "@calendar_gantt/views/gantt/gantt_controller";
import {
    AppointmentBookingGanttModel,
    AppointmentResourceBookingGanttModel,
} from "@calendar_gantt/views/gantt/gantt_model";
import { AppointmentBookingGanttRenderer } from "@calendar_gantt/views/gantt/gantt_renderer";
import { registry } from "@web/core/registry";
import { ganttView } from "@web_gantt/gantt_view";

export const AppointmentBookingGanttView = {
    ...ganttView,
    Controller: AppointmentBookingGanttController,
    Model: AppointmentBookingGanttModel,
    Renderer: AppointmentBookingGanttRenderer,
};

registry
    .category("views")
    .add("appointment_booking_gantt", AppointmentBookingGanttView);

registry.category("views").add("resource_booking_gantt", {
    ...AppointmentBookingGanttView,
    Model: AppointmentResourceBookingGanttModel,
});
