/** @odoo-module native */
import { attendeeCalendarView } from "@calendar/views/attendee_calendar/attendee_calendar_view";
import { POSAttendeeCalendarController } from "@pos_appointment/app/calendar_extend/calendar_controller";
import { registry } from "@web/core/registry";

export const posAttendeeCalendarView = {
    ...attendeeCalendarView,
    Controller: POSAttendeeCalendarController,
};

registry
    .category("views")
    .add("pos_appointment_attendee_calendar", posAttendeeCalendarView);
