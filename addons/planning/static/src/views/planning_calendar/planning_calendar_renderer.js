/** @odoo-module native */
import { PlanningCalendarCommonRenderer } from "@planning/views/planning_calendar/common/planning_calendar_common_renderer";
import { CalendarRenderer } from "@web/views/calendar";

export class PlanningCalendarRenderer extends CalendarRenderer {
    static components = {
        ...CalendarRenderer.components,
        day: PlanningCalendarCommonRenderer,
        week: PlanningCalendarCommonRenderer,
        month: PlanningCalendarCommonRenderer,
    };
}
