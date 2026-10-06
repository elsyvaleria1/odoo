/** @odoo-module native */

import { AppointmentBookingGanttRenderer } from "@calendar_gantt/views/gantt/gantt_renderer";
import { patch } from "@web/core/utils/patch";

patch(AppointmentBookingGanttRenderer, {
    rowContentTemplate: "pos_gantt.GanttRenderer.RowContent",
});

patch(AppointmentBookingGanttRenderer.prototype, {
    setup() {
        super.setup();
        this.orders = posmodel.models["pos.order"].getAll();
    },

    isBooked(column, row) {
        return (
            column.isToday &&
            this.orders.some(
                (o) =>
                    o.table_id?.resource_id.id === row.resId &&
                    !o.finalized &&
                    o.isBooked,
            )
        );
    },
});
