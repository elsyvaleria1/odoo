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
    /**
     * @override
     * Prevent creation of record if the user does not have write access on the
     * parent record (readonly knowledge articles for example) and if the model
     * props are invalid
     */
    get canCreate() {
        if (this.meta.invalid) {
            return false;
        }
        return this.meta.canCreate;
    }
    /**
     * @override
     * Usually, records cannot be edited if the start field is readonly (which
     * is a property shared by every record of the current calendar). In this
     * case however, it depends on the record (eg. users cannot edit readonly
     * knowledge articles). Therefore, we always allow users to edit the record
     * but we show an access error if the user tried to edit a readonly record.
     */
    get canEdit() {
        return true;
    }

    /**
     * @override
     * Show the "all day" slot in "day" and "week" scales even if the date is a
     * datetime, as there is no "allDay" option in this model.
     */
    get hasAllDaySlot() {
        return true;
    }

    /**
     * @override
     * Build a raw record from the given partial record and the properties. We
     * need every property of the record when editing a record otherwise we
     * will lose the values of these properties when writing on the record
     * (since the properties are stored as json objects).
     */
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

    /**
     * @override
     * Normalize the given raw record with the properties
     */
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

    /**
     * @override
     * Compute the domain used to fetch the items using the properties used as
     * start and end date. The properties definition is used in the domain to
     * make sure to not match records that still use the "previous" dateStart
     * property when this property has been changed (if the type of a property
     * changed, the property will be replaced by a new one but the change will
     * be propagated to the records using that property when writing on them)
     */
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
