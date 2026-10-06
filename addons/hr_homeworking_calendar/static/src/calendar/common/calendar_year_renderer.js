/** @odoo-module native */
import { attendeeCalendarYearRendererProps } from "@calendar/views/attendee_calendar/year/attendee_calendar_year_renderer";
import { t } from "@odoo/owl";

Object.assign(attendeeCalendarYearRendererProps, {
    openWorkLocationWizard: t.function().optional(),
});
