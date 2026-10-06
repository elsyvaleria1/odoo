/** @odoo-module native */
import { WorkEntryCalendarCommonRenderer } from "@hr_work_entry/views/work_entry_calendar/calendar_common/work_entry_calendar_common_renderer";
import { t } from "@odoo/owl";
import { CalendarRenderer } from "@web/views/calendar";

export class WorkEntryCalendarRenderer extends CalendarRenderer {
    static components = {
        ...CalendarRenderer.components,
        month: WorkEntryCalendarCommonRenderer,
    };
    static props = { ...CalendarRenderer.props, splitRecord: t.function() };
}
