/** @odoo-module native */
import { CalendarController } from "@web/views/calendar";

import { TimesheetCalendarMyTimesheetsSidePanel } from "./timesheet_calendar_my_timesheets_side_panel.js";

export class TimesheetCalendarMyTimesheetsController extends CalendarController {
    static components = {
        ...CalendarController.components,
        CalendarSidePanel: TimesheetCalendarMyTimesheetsSidePanel,
    };
}
