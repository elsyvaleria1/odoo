/** @odoo-module native */
import { AppointmentBookingGanttRenderer } from "@calendar_gantt/views/gantt/gantt_renderer";
import * as dates from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { isHtmlEmpty } from "@web/core/utils/dom/html";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

export class POSAppointmentBookingGanttRenderer extends AppointmentBookingGanttRenderer {
    static pillTemplate = "pos_gantt.GanttRenderer.Pill";
    static rowHeaderTemplate = "pos_gantt.GanttRenderer.RowHeader";
    static components = {
        ...AppointmentBookingGanttRenderer.components,
        Popover: GanttRenderer.components.Popover,
    };

    async getPopoverProps(pill) {
        const props = await super.getPopoverProps(...arguments);
        const { record } = pill;
        const now = dates.now();
        delete props.headerClass;
        props.context.isHtmlEmpty = isHtmlEmpty;
        props.context.dates = dates;
        props.buttons = [
            {
                class: "btn btn-sm btn-primary",
                onClick: () => this.props.openDialog({ resId: record.id }),
                text: this.model.metaData.canEdit ? _t("Edit") : _t("View"),
            },
            {
                class: "o_appointment_booking_confirm_status btn btn-sm btn-danger",
                onClick: () => {
                    this.orm
                        .write("calendar.event", [record.id], {
                            active: false,
                            appointment_status: "cancelled",
                        })
                        .then(() => this.model.fetchData());
                },
                text: _t("Delete"),
            },
            {
                class:
                    "o_appointment_booking_confirm_status btn btn-sm btn-group ms-4" +
                    (record.appointment_status === "booked"
                        ? " o_gantt_color_" +
                          (dates.diff(now, record.start, "minutes") > 15 ? 2 : 4)
                        : ""),
                onClick: () => {
                    this.orm
                        .write("calendar.event", [record.id], {
                            appointment_status: "booked",
                        })
                        .then(() => this.model.fetchData());
                },
                text: _t("Booked"),
            },
            {
                class:
                    "o_appointment_booking_confirm_status btn btn-sm btn-group" +
                    (record.appointment_status === "attended"
                        ? " o_gantt_color_10"
                        : ""),
                onClick: () => {
                    this.orm
                        .write("calendar.event", [record.id], {
                            appointment_status: "attended",
                        })
                        .then(() => this.model.fetchData());
                },
                text: _t("Check In"),
            },
            {
                class:
                    "o_appointment_booking_confirm_status btn btn-sm btn-group" +
                    (record.appointment_status === "no_show" ? " o_gantt_color_1" : ""),
                onClick: () => {
                    this.orm
                        .write("calendar.event", [record.id], {
                            appointment_status: "no_show",
                        })
                        .then(() => this.model.fetchData());
                },
                text: _t("No Show"),
            },
        ];
        return props;
    }
}
