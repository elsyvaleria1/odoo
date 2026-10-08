/** @odoo-module native */
import { AttendeeCalendarCommonPopover } from "@calendar/views/attendee_calendar/common/attendee_calendar_common_popover";
import { patch } from "@web/core/utils/patch";

patch(AttendeeCalendarCommonPopover.prototype, {
    get isEventArchivable() {
        // an external calendar holds the event: archiving it deletes it there
        return (
            super.isEventArchivable ||
            (this.isCurrentUserOrganizer &&
                this.props.record.rawRecord.calendar_sync_linked)
        );
    },
});
