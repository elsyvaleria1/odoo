/** @odoo-module native */
import { AppointmentSyncButton } from "@calendar/booking/components/appointment_sync_button/appointment_sync_button";
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardWidgetProps } from "@web/views/widgets";

/** A button per provider a staff member may connect their calendar to. */
export class CalendarSyncAppointmentButtons extends Component {
    static components = { AppointmentSyncButton };
    static props = { ...standardWidgetProps };
    static template = "calendar_sync.AppointmentButtons";
    props = useProps(this.constructor.props);

    get connectors() {
        return this.props.record.data.calendar_sync_connectors || [];
    }

    routeOf(connector) {
        return `/calendar_sync/${connector.code}/sync_data`;
    }
}

registry.category("view_widgets").add("calendar_sync_appointment_buttons", {
    component: CalendarSyncAppointmentButtons,
});
