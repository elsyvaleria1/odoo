/** @odoo-module native */
import { timesheetCalendarView } from "@hr_timesheet/views/timesheet_calendar/timesheet_calendar_view";
import { patch } from "@web/core/utils/patch";

import { TimesheetCalendarMyTimesheetsController } from "../timesheet_calendar_my_timesheets/timesheet_calendar_my_timesheets_controller.js";

patch(timesheetCalendarView, { Controller: TimesheetCalendarMyTimesheetsController });
