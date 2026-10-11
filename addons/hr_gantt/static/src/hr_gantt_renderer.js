/** @odoo-module native */
import { isDateTimeValue, maxDate, minDate } from "@web/core/l10n/dates";
import { GanttRenderer } from "@web_gantt/gantt_renderer";

import { GanttEmployeeAvatar } from "./hr_gantt_employee_avatar.js";

export class HrGanttRenderer extends GanttRenderer {
    static components = { ...GanttRenderer.components, Avatar: GanttEmployeeAvatar };

    static LUNCH_BREAK_START_HOUR = 11;
    static LUNCH_BREAK_STOP_HOUR = 14;

    getRowAvatar(row) {
        const { groupedByField, name, resId } = row;
        const { fields } = this.model.metaData;
        const relation = groupedByField && fields[groupedByField]?.relation;
        if (Boolean(resId) && relation === "hr.employee") {
            return { resModel: relation, resId, displayName: name };
        }
        return null;
    }

    /**
     * @param {RelationalRecord} record
     * @returns {Partial<Pill>}
     */
    getPill(record) {
        const pill = super.getPill(record);
        const { unit, cellPart } = this.model.metaData.scale;
        const [startIndex, endIndex] = pill.grid.column;
        const { dateStartField, dateStopField, globalStart, globalStop } =
            this.model.metaData;
        if (
            isDateTimeValue(record[dateStartField]) &&
            isDateTimeValue(record[dateStopField]) &&
            cellPart === 2 &&
            ["week", "month"].includes(unit) &&
            endIndex - startIndex === 2
        ) {
            const start = maxDate(globalStart, record[dateStartField]);
            const stop = minDate(globalStop, record[dateStopField]);
            if (start.day === stop.day) {
                const startTime = start.hour + start.minute / 60;
                const stopTime = stop.hour + stop.minute / 60;
                const { LUNCH_BREAK_START_HOUR, LUNCH_BREAK_STOP_HOUR } =
                    this.constructor;
                const closestToNoon =
                    12 - startTime < stopTime - 12 ? startTime : stopTime;
                if (
                    startTime >= LUNCH_BREAK_START_HOUR &&
                    startTime === closestToNoon
                ) {
                    pill.grid.column = [startIndex + 1, endIndex];
                } else if (stopTime <= LUNCH_BREAK_STOP_HOUR) {
                    pill.grid.column = [startIndex, endIndex - 1];
                }
            }
        }
        return pill;
    }
}
