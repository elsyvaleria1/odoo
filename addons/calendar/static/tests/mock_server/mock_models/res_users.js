import { mailModels } from "@mail/../tests/mail_test_helpers";
import { serverState } from "@web/../tests/web_test_helpers";
import { dateTime, serializeDateTime } from "@web/core/l10n/dates";

export class ResUsers extends mailModels.ResUsers {
    /**
     * Simulates `_systray_get_calendar_event_domain` on `res.users`.
     *
     * @private
     */
    _systray_get_calendar_event_domain() {
        const startDate = dateTime({ hour: 0, minute: 0, second: 0, millisecond: 0 });
        const endDate = dateTime({
            hour: 23,
            minute: 59,
            second: 59,
            millisecond: 999,
        });

        const currentPartnerAttendeeIds = this.env["calendar.attendee"].search([
            ["partner_id", "=", serverState.partnerId],
            ["state", "!=", "declined"],
        ]);
        return [
            "&",
            "|",
            "&",
            "|",
            ["start", ">=", serializeDateTime(startDate)],
            ["stop", ">=", serializeDateTime(startDate)],
            ["start", "<=", serializeDateTime(endDate)],
            ["attendee_ids", "in", [...currentPartnerAttendeeIds]],
        ];
    }

    /** @override */
    _get_activity_groups() {
        const activities = super._get_activity_groups();
        const meetingsLines = this.env["calendar.event"].search_read(
            this._systray_get_calendar_event_domain(),
            {
                fields: ["id", "start", "name", "allday"],
                order: "start",
            },
        );
        if (meetingsLines.length) {
            activities.unshift({
                id: "calendar.event",
                meetings: meetingsLines,
                model: "calendar.event",
                name: "Today's Meetings",
                type: "meeting",
            });
        }
        return activities;
    }
}
