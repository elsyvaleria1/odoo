/** @odoo-module native */
import { AttendeeCalendarController } from "@calendar/views/attendee_calendar/attendee_calendar_controller";
import { patch } from "@web/core/utils/patch";

patch(AttendeeCalendarController.prototype, {
    getOpportunityName() {
        if (!this.props.context.default_opportunity_id) {
            return undefined;
        }
        return this.props.context.default_name;
    },
});
