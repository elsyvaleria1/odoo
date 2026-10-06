import { CalendarEvent } from "@pos_appointment/../tests/unit/data/calendar_event.data";
import { now, serializeDateTime } from "@web/core/l10n/dates";

export const applyRestaurantAppointmentCalendarEventRecords = () => {
    CalendarEvent._records = [
        {
            id: 1,
            start: serializeDateTime(now()),
            duration: 4.0,
            stop: serializeDateTime(now().add({ hours: 4 })),
            name: "Test appointment",
            appointment_status: "booked",
            resource_ids: [1],
            total_capacity_reserved: 2,
        },
        {
            id: 2,
            start: serializeDateTime(now().subtract({ days: 1 })),
            duration: 4.0,
            stop: serializeDateTime(now().subtract({ days: 1 }).add({ hours: 4 })),
            name: "Test appointment",
            appointment_status: "booked",
            resource_ids: [1],
            total_capacity_reserved: 2,
        },
        {
            id: 3,
            start: serializeDateTime(now()),
            duration: 2.0,
            stop: serializeDateTime(now().add({ hours: 4 })),
            name: "Test appointment",
            appointment_status: "attended",
            resource_ids: [2],
            total_capacity_reserved: 2,
        },
        {
            id: 4,
            start: serializeDateTime(now()),
            duration: 2.0,
            stop: serializeDateTime(now().add({ hours: 4 })),
            name: "Test appointment",
            appointment_status: "no_show",
            resource_ids: [2],
            total_capacity_reserved: 2,
        },
    ];
};
