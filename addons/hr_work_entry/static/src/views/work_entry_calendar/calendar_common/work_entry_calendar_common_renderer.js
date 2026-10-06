/** @odoo-module native */
import { WorkEntryCalendarCommonPopover } from "@hr_work_entry/views/work_entry_calendar/calendar_common/work_entry_calendar_common_popover";
import { t } from "@odoo/owl";
import { CalendarCommonRenderer, convertRecordToEvent } from "@web/views/calendar";

export class WorkEntryCalendarCommonRenderer extends CalendarCommonRenderer {
    static eventTemplate = "hr_work_entry.WorkEntryCalendarCommonRenderer.event";
    static components = {
        ...CalendarCommonRenderer.components,
        Popover: WorkEntryCalendarCommonPopover,
    };
    static props = { ...CalendarCommonRenderer.props, splitRecord: t.function() };

    /** @override */
    convertRecordToEvent(record) {
        const event = convertRecordToEvent(record);
        const editable =
            record.rawRecord.state !== "validated" && (event.editable ?? null);
        return {
            ...event,
            ...(editable ? { editable: editable } : {}),
        };
    }

    getPopoverProps(record) {
        return {
            ...super.getPopoverProps(record),
            splitRecord: this.props.splitRecord,
        };
    }
}
