/** @odoo-module native */
import { AppointmentBookingActionHelper } from "@calendar/booking/components/appointment_booking_action_helper/appointment_booking_action_helper";
import {
    CalendarQuickCreate,
    QUICK_CREATE_CALENDAR_EVENT_FIELDS,
} from "@calendar/views/calendar_form/calendar_quick_create";
import { now as getNow } from "@web/core/l10n/dates";
import { GanttController } from "@web_gantt/gantt_controller";

Object.assign(QUICK_CREATE_CALENDAR_EVENT_FIELDS, {
    appointment_status: { type: "string" },
    resource_ids: { type: "many2many" },
    total_capacity_reserved: { type: "number" },
});

export class AppointmentBookingGanttController extends GanttController {
    static template = "calendar.booking.AppointmentBookingGanttController";
    static components = {
        ...GanttController.components,
        AppointmentBookingActionHelper,
    };
    /**
     * @override
     */
    create(context) {
        super.create({ ...context, booking_gantt_create_record: true });
    }

    /** @override */
    get showNoContentHelp() {
        if (
            !this.props.context.hide_no_content_helper &&
            this.props.context.active_model === "appointment.type"
        ) {
            return !this.model.data.records.length;
        } else {
            return (
                !this.model.data.rows ||
                (this.model.data.rows.length === 1 && !this.model.data.rows[0].name)
            );
        }
    }

    /** @override */
    createAtFocusDate() {
        const focusDate = this.getCurrentFocusDate();
        const now = getNow();
        const start =
            now.minute > 30
                ? focusDate
                      .with({ hour: now.hour, minute: 0, second: 0 })
                      .add({ hours: 1 })
                : focusDate.with({ hour: now.hour, minute: 30, second: 0 });
        const stop = start.add({ hours: 1 });
        const context = this.model.getDialogContext({ start, stop, withDefault: true });
        this.create(context);
    }

    /** @override */
    openDialog(props, options = {}, dialogComponent = null) {
        if (dialogComponent !== null) {
            return super.openDialog(...arguments);
        }
        return super.openDialog(props, options, CalendarQuickCreate);
    }
}
