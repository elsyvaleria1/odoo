// @ts-check
/** @odoo-module native */

export function getAttendeeStatusClass(record) {
    if (record.isAlone) {
        return "o_attendee_status_alone";
    }
    return `o_attendee_status_${record.attendeeStatus}`;
}
