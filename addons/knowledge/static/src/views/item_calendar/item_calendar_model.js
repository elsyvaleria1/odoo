/** @odoo-module native */
import {
    deserializeDate,
    deserializeDateTime,
    serializeDate,
    serializeDateTime,
    toDateTime,
} from "@web/core/l10n/dates";
import { CalendarModel } from "@web/views/calendar";

export class ItemCalendarModel extends CalendarModel {
    /** @override */
    get canCreate() {
        if (this.meta.invalid) {
            return false;
        }
        return this.meta.canCreate;
    }
    /** @override */
    get canEdit() {
        return true;
    }

    /** @override */
    get hasAllDaySlot() {
        return true;
    }

    /** @override */
    buildRawRecord(partialRecord) {
        let start = partialRecord.start;
        let end = partialRecord.end;

        if (!end) {
            if (this.meta.propertiesDateType === "date") {
                end = start;
            } else {
                end = start.add({ hours: 1 });
            }
        }

        if (this.meta.propertiesDateType === "datetime" && partialRecord.isAllDay) {
            if (partialRecord.id) {
                start = start.with({
                    hour: this.data.records[partialRecord.id].start.hour,
                });
                end = end.with({ hour: this.data.records[partialRecord.id].end.hour });
            } else {
                start = start.with({ hour: 7 });
                end = end.with({ hour: 19 });
            }
        }

        start =
            this.meta.propertiesDateType === "date"
                ? serializeDate(start)
                : serializeDateTime(start);
        end =
            this.meta.propertiesDateType === "date"
                ? serializeDate(end)
                : serializeDateTime(end);

        let properties = {};

        if (partialRecord.id) {
            properties =
                this.data.records[partialRecord.id].rawRecord.article_properties;
            properties.find(
                (property) => property.name === this.meta.fieldMapping.date_start,
            ).value = start;

            if (this.meta.fieldMapping.date_stop) {
                properties.find(
                    (property) => property.name === this.meta.fieldMapping.date_stop,
                ).value = end;
            }
        } else {
            properties[this.meta.fieldMapping.date_start] = start;
            if (this.meta.fieldMapping.date_stop) {
                properties[this.meta.fieldMapping.date_stop] = end;
            }
        }
        return { article_properties: properties };
    }

    loadRecords(data) {
        if (this.meta.invalid) {
            return {};
        }
        return super.loadRecords(data);
    }

    /** @override */
    normalizeRecord(rawRecord) {
        const { fieldMapping, propertiesDateType, scale } = this.meta;
        const isDate = propertiesDateType === "date";

        const startValue = rawRecord.article_properties.find(
            (property) => property.name === fieldMapping.date_start,
        )?.value;
        const stopValue = rawRecord.article_properties.find(
            (property) => property.name === fieldMapping.date_stop,
        )?.value;
        const deserialize = (value) =>
            isDate ? toDateTime(deserializeDate(value)) : deserializeDateTime(value);
        const start = deserialize(startValue);

        const end = stopValue ? deserialize(stopValue) : start;

        const showTime = scale === "month" && !isDate;

        const colorValue = rawRecord.article_properties.find(
            (property) => property.name === fieldMapping.color,
        )?.value;
        const colorIndex = Array.isArray(colorValue) ? colorValue[0] : colorValue;

        return {
            id: rawRecord.id,
            title: rawRecord.display_name,
            isAllDay: isDate,
            start,
            startType: propertiesDateType,
            end,
            endType: propertiesDateType,
            colorIndex,
            isTimeHidden: !showTime,
            rawRecord,
        };
    }

    /** @override */
    computeRangeDomain(data) {
        const { fieldMapping } = this.meta;
        const formattedEnd = serializeDateTime(data.range.end);
        const formattedStart = serializeDateTime(data.range.start);

        const domain = [
            [`article_properties.${fieldMapping.date_start}`, "<=", formattedEnd],
            [
                "parent_id.article_properties_definition",
                "ilike",
                `"${fieldMapping.date_start}"`,
            ],
        ];
        if (fieldMapping.date_stop) {
            domain.push(
                [`article_properties.${fieldMapping.date_stop}`, ">=", formattedStart],
                [
                    "parent_id.article_properties_definition",
                    "ilike",
                    `"${fieldMapping.date_stop}"`,
                ],
            );
        }
        return domain;
    }
}
