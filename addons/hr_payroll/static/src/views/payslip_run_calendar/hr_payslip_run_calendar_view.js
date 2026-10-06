/** @odoo-module native */
import { registry } from "@web/core/registry";
import { calendarView } from "@web/views/calendar";

import { PayRunCalendarController } from "./hr_payslip_run_calendar_controller.js";

const PayRunCalendarView = {
    ...calendarView,
    Controller: PayRunCalendarController,
    buttonTemplate: "hr_payroll.PayRunCalendarView.Buttons",
};

registry.category("views").add("pay_run_calendar", PayRunCalendarView);
