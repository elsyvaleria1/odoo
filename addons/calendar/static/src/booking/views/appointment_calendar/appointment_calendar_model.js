/** @odoo-module native */
import { AttendeeCalendarModel } from "@calendar/views/attendee_calendar/attendee_calendar_model";
import {
    diff,
    formatValue,
    hasSame,
    isDateOrDateTimeValue,
} from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(AttendeeCalendarModel.prototype, {
    /**
     * @override
     */
    setup() {
        super.setup(...arguments);
        this.data.slots = {};
        this.defaultSlotDurationMinutes = 30;
        this.slotId = 1;
    },

    /**
     * @override
     * Properly take into account the duration from the context.
     * Only when the user makes a click on the calendar (when there's no end) or when the end is invalid.
     */
    buildRawRecord(partialRecord) {
        if ("default_duration" in this.meta.context) {
            const defaultDuration = this.meta.context.default_duration;
            if (
                partialRecord.start &&
                !isDateOrDateTimeValue(partialRecord.end) &&
                !partialRecord.isAllDay
            ) {
                partialRecord.end = partialRecord.start.add({
                    milliseconds: Math.round(defaultDuration * 3600000),
                });
            }
        }
        return super.buildRawRecord(...arguments);
    },

    processPartialSlotRecord(record) {
        if (!isDateOrDateTimeValue(record.end)) {
            if (record.isAllDay) {
                record.end = record.start;
            } else {
                record.end = record.start.add({
                    milliseconds: Math.round(this.defaultSlotDurationMinutes * 60000),
                });
            }
        }
        if (!record.isAllDay) {
            record.title = "";
            if (diff(record.end, record.start, "hours") >= 24) {
                record.title =
                    formatValue(record.start, "EEE d, t") +
                    " - " +
                    formatValue(record.end, "EEE d, t");
            }
            if (record.start && record.end) {
                this.defaultSlotDurationMinutes = diff(
                    record.end,
                    record.start,
                    "minutes",
                );
            }
        } else {
            const isSameDay = hasSame(record.start, record.end, "day");
            if (!isSameDay && hasSame(record.start, record.end, "month")) {
                // Simplify date-range if an event occurs into the same month (eg. "August, 4-5 2019")
                record.title =
                    formatValue(record.start, "LLLL d") +
                    "-" +
                    formatValue(record.end, "d, y");
            } else {
                record.title = isSameDay
                    ? formatValue(record.start, "DDD")
                    : formatValue(record.start, "DDD") +
                      " - " +
                      formatValue(record.end, "DDD");
            }
        }
    },

    createSlot(record) {
        this.processPartialSlotRecord(record);
        const slotId = this.slotId++;
        this.data.slots = {
            ...this.data.slots,
            [slotId]: {
                id: slotId,
                title: record.title,
                start: record.start,
                end: record.end,
                isAllDay: record.isAllDay,
            },
        };
        this.notify();
        return this.data.slots[slotId];
    },

    updateSlot(eventRecord) {
        this.processPartialSlotRecord(eventRecord);
        const slot = this.data.slots[eventRecord.slotId];
        Object.assign(slot, {
            title: eventRecord.title,
            start: eventRecord.start,
            end: eventRecord.end,
            isAllDay: eventRecord.isAllDay,
        });
        this.data.slots = { ...this.data.slots };
        this.notify();
    },

    removeSlot(slotId) {
        const slots = { ...this.data.slots };
        delete slots[slotId];
        this.data.slots = slots;
        this.notify();
    },

    clearSlots() {
        this.data.slots = {};
        this.notify();
    },
});
