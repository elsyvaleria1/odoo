/** @odoo-module native */
import { defineScope } from "@web/core/scope";

const envScope = defineScope(
    "calendar/booking/views/appointment_calendar/appointment_calendar_context",
);

/** @param {Record<string, any>} context */
export function provideAppointmentCalendarContext(context) {
    envScope.provide(context);
}

/** @param {Record<string, any>} context */
export function provideChildAppointmentCalendarContext(context) {
    envScope.provide(context);
}

/** @returns {Record<string, any>} */
export function useAppointmentCalendarContext() {
    return envScope.use();
}
