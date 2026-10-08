/** @odoo-module native */
import { getMin } from "@point_of_sale/utils";
import { FloorScreen } from "@pos_restaurant/app/screens/floor_screen/floor_screen";
import { compareDates, formatValue, now } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(FloorScreen.prototype, {
    async _createTableHelper() {
        const table = await super._createTableHelper(...arguments);
        if (!table) {
            return table;
        }
        const appointmentRessource = this.pos.models["resource.resource"].get(
            table.resource_id?.id,
        );

        if (!appointmentRessource) {
            await this.pos.data.searchRead(
                "resource.resource",
                [["pos_table_ids", "in", table.id]],
                this.pos.data.fields["resource.resource"],
                { limit: 1 },
            );
        }

        return table;
    },
    async duplicateFloor() {
        await super.duplicateFloor(...arguments);
        const tableIds = this.activeTables.map((table) => table.id);

        if (tableIds.length > 0) {
            await this.pos.data.searchRead(
                "resource.resource",
                [["pos_table_ids", "in", tableIds]],
                this.pos.data.fields["resource.resource"],
            );
        }
    },
    async createTableFromRaw(table) {
        delete table.resource_id;
        return super.createTableFromRaw(table);
    },

    getFirstAppointment(table) {
        if (!table.resource_id) {
            return false;
        }
        const appointments = this.pos.models["calendar.event"].getBy(
            "resource_ids",
            table.resource_id.id,
        );
        if (!appointments) {
            return false;
        }
        const startOfToday = now().with({ hour: 0, minute: 0, second: 0 });
        appointments.map((appointment) => {
            if (compareDates(appointment.start, startOfToday) < 0) {
                appointment.start = startOfToday;
            }
        });
        const dt_now = now();
        const dt_tomorrow_ts = dt_now
            .add({ days: 1 })
            .with({ hour: 0, minute: 0, second: 0 }).epochMilliseconds;
        const possible_appointments = appointments.filter((a) => {
            const ts_now = dt_now.epochMilliseconds - (a.duration / 2) * 3600000;
            const dt_ts = a.start.epochMilliseconds;
            return (
                dt_ts > ts_now &&
                dt_ts < dt_tomorrow_ts &&
                a.appointment_status !== "no_show" &&
                a.appointment_status !== "attended"
            );
        });
        if (possible_appointments.length === 0) {
            return false;
        }
        return getMin(possible_appointments, {
            criterion: (a) => a.start.epochMilliseconds,
        });
    },
    getFormattedDate(date) {
        return formatValue(date, "HH:mm");
    },
    isCustomerLate(table) {
        const dateNow = now();
        const dateStart = this.getFirstAppointment(table)?.start;
        return (
            Boolean(dateStart) &&
            compareDates(dateNow, dateStart) > 0 &&
            this.getFirstAppointment(table).appointment_status === "booked"
        );
    },
    onClickAppointment(ev, table) {
        if (!this.pos.isEditMode) {
            ev.stopPropagation();
            return this.pos.editBooking(this.getFirstAppointment(table));
        }
    },
});
