/** @odoo-module native */
import {
    Many2ManyAttendee,
    many2ManyAttendee,
} from "@calendar/views/fields/many2many_attendee";
import { proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";

export class Many2ManyAttendeeExpandable extends Many2ManyAttendee {
    static template = "calendar.Many2ManyAttendeeExpandable";
    state = proxy({ expanded: false });

    get attendeesCount() {
        return this.props.record.data.attendees_count;
    }

    get acceptedCount() {
        return this.props.record.data.accepted_count;
    }

    get declinedCount() {
        return this.props.record.data.declined_count;
    }

    get uncertainCount() {
        return this.attendeesCount - this.acceptedCount - this.declinedCount;
    }

    onExpanderClick() {
        this.state.expanded = !this.state.expanded;
    }
}

export const many2ManyAttendeeExpandable = {
    ...many2ManyAttendee,
    component: Many2ManyAttendeeExpandable,
};

registry
    .category("fields")
    .add("many2manyattendeeexpandable", many2ManyAttendeeExpandable);
