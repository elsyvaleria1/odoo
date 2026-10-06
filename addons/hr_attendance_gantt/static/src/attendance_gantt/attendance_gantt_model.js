/** @odoo-module native */
import { Domain } from "@web/core/domain";
import { compareDates, now, serializeDateTime, toISODate } from "@web/core/l10n/dates";
import { GanttModel, parseServerValues } from "@web_gantt/gantt_model";

export class AttendanceGanttModel extends GanttModel {
    //-------------------------------------------------------------------------
    // Protected
    //-------------------------------------------------------------------------

    /**
     * @override
     */
    _getDomain(metaData) {
        const { dateStartField, dateStopField, globalStart, globalStop } = metaData;
        const dateNow = now();
        if (compareDates(dateNow, globalStart) >= 0) {
            const domain = Domain.and([
                this.searchParams.domain,
                [
                    "&",
                    [dateStartField, "<", serializeDateTime(globalStop)],
                    "|",
                    "&",
                    [dateStartField, "<", serializeDateTime(dateNow)],
                    [dateStopField, "=", false],
                    [dateStopField, ">", serializeDateTime(globalStart)],
                ],
            ]);
            return domain.toList();
        } else {
            return super._getDomain(...arguments);
        }
    }

    async _fetchData(metaData) {
        const startDate = toISODate(metaData.globalStart);
        const activeDomain = [];
        if (
            !this.searchParams.domain.some(
                (index) => Array.isArray(index) && index[0] === "employee_id.active",
            )
        ) {
            activeDomain.push(["employee_id.active", "=", true]);
        }
        const context = {
            gantt_start_date: startDate,
            user_domain: this.searchParams.domain,
            active_domain: activeDomain,
        };
        await super._fetchData(metaData, context);
    }

    _parseServerData(metaData, records) {
        const { dateStartField, dateStopField, fields } = metaData;
        /** @type {Record<string, any>[]} */
        const parsedRecords = super._parseServerData(...arguments);
        for (const record of records) {
            const parsedRecord = parseServerValues(fields, record);
            const dateStart = parsedRecord[dateStartField];
            const dateStop = parsedRecord[dateStopField];
            if (dateStart && !dateStop) {
                parsedRecord[dateStopField] = now();
                parsedRecords.push(parsedRecord);
            }
        }
        return parsedRecords;
    }

    get rangeSpan() {
        return { before: 0, count: 1 };
    }
}
