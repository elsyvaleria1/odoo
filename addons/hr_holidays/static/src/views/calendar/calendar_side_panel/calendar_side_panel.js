/** @odoo-module native */
import { onWillStart, onWillUpdateProps, proxy } from "@odoo/owl";
import {
    hasSame,
    isDateTimeValue,
    parseISO,
    serializeDate,
    serializeDateTime,
    toLocaleString,
} from "@web/core/l10n/dates";
import { Cache } from "@web/core/utils/collections/cache";
import { useService } from "@web/core/utils/hooks";
import { CalendarSidePanel } from "@web/views/calendar";

import { TimeOffCalendarFilterSection } from "../filter_section/calendar_filter_section.js";

// the cache hands back the same objects on a hit, already read
export function readDate(value) {
    return isDateTimeValue(value) ? value : parseISO(value);
}

export class TimeOffCalendarSidePanel extends CalendarSidePanel {
    static components = {
        ...CalendarSidePanel.components,
        FilterSection: TimeOffCalendarFilterSection,
    };
    static template = "hr_holidays.TimeOffCalendarSidePanel";

    setup() {
        super.setup();

        this.orm = useService("orm");
        this.getFormattedDateSpan = function getFormattedDateSpan(start, end) {
            const n = "numeric";
            const s = "short";
            const isSameDay = hasSame(start, end, "day");
            if (isSameDay) {
                return toLocaleString(start, { month: s, day: n, year: n });
            }
            return (
                toLocaleString(start, { month: s, day: n, year: n }) +
                " - " +
                toLocaleString(end, { month: s, day: n, year: n })
            );
        };
        this.leaveState = proxy({
            mandatoryDays: [],
            bankHolidays: [],
        });

        this._specialDaysCache = new Cache(
            (start, end) => this.fetchSpecialDays(start, end),
            (start, end) => `${serializeDateTime(start)},${serializeDateTime(end)}`,
        );

        onWillStart(this.updateSpecialDays);
        onWillUpdateProps(this.updateSpecialDays);
    }

    fetchSpecialDays(start, end) {
        const context = {
            employee_id: this.props.model.employeeId,
        };
        return this.orm.call(
            "hr.employee",
            "get_special_days_data",
            [serializeDate(start, "datetime"), serializeDate(end, "datetime")],
            {
                context: context,
            },
        );
    }

    async updateSpecialDays() {
        const { rangeStart, rangeEnd } = this.props.model;
        const specialDays = await this._specialDaysCache.read(rangeStart, rangeEnd);
        specialDays["bankHolidays"].forEach((bankHoliday) => {
            bankHoliday.start = readDate(bankHoliday.start);
            bankHoliday.end = readDate(bankHoliday.end);
        });
        specialDays["mandatoryDays"].forEach((mandatoryDay) => {
            mandatoryDay.start = readDate(mandatoryDay.start);
            mandatoryDay.end = readDate(mandatoryDay.end);
        });
        this.leaveState.bankHolidays = specialDays["bankHolidays"];
        this.leaveState.mandatoryDays = specialDays["mandatoryDays"];
    }
}
