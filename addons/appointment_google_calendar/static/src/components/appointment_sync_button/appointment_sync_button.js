/** @odoo-module native */
import { AppointmentSyncButton } from "@calendar/booking/components/appointment_sync_button/appointment_sync_button";
import { patch } from "@web/core/utils/patch";

patch(AppointmentSyncButton.prototype, {
    _getCalendarSyncData(calendarName) {
        if (calendarName === "Google") {
            return {
                noNewEventKey: "no_new_event_from_google",
                syncRoute: "/google_calendar/sync_data",
            };
        }
        return super._getCalendarSyncData(...arguments);
    },
});
