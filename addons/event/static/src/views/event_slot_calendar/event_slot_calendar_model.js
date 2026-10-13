/** @odoo-module native */
import { resolveZone, serializeDate, userTimeZone } from "@web/core/l10n/dates";
import { CalendarModel } from "@web/views/calendar";

export class EventSlotCalendarModel extends CalendarModel {
    /** @override */
    buildRawRecord(partialRecord, options = {}) {
        const rawRecord = super.buildRawRecord(partialRecord, options);
        rawRecord["date"] = serializeDate(partialRecord.start);
        rawRecord["start_hour"] =
            partialRecord.start.hour + partialRecord.start.minute / 60;
        if (partialRecord.end) {
            rawRecord["end_hour"] =
                partialRecord.end.hour + partialRecord.end.minute / 60;
        }
        return rawRecord;
    }

    /** @override */
    makeContextDefaults(rawRecord) {
        const context = super.makeContextDefaults(rawRecord);
        context["default_date"] = rawRecord["date"];
        return context;
    }

    /** @override */
    normalizeRecord(rawRecord) {
        const normalizedRecord = super.normalizeRecord(rawRecord);
        const tz = resolveZone(rawRecord.date_tz || "utc");
        const localZone = userTimeZone();
        normalizedRecord.start = normalizedRecord.start
            .withTimeZone(tz)
            .toPlainDateTime()
            .toZonedDateTime(localZone);
        normalizedRecord.end = normalizedRecord.end
            .withTimeZone(tz)
            .toPlainDateTime()
            .toZonedDateTime(localZone);
        normalizedRecord.isTimeHidden = false;
        return normalizedRecord;
    }
}
