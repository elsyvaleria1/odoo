/** @odoo-module native */
import { AttendeeCalendarModel } from "@calendar/views/attendee_calendar/attendee_calendar_model";
import {
    compareDates,
    endOf,
    serializeDateTime,
    toISODate,
} from "@web/core/l10n/dates";
import { user } from "@web/core/user";
import { patch } from "@web/core/utils/patch";
import { getColor } from "@web/views/calendar";

const WEEKDAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
];

patch(AttendeeCalendarModel.prototype, {
    fetchEventLocation(data) {
        let attendeeIds;
        const filters = data.filterSections.partner_ids?.filters;
        if (
            filters &&
            filters[filters.length - 1].type === "all" &&
            filters[filters.length - 1].active
        ) {
            attendeeIds = Object.keys(this.partnerColorMap).map(Number);
        } else {
            attendeeIds = (filters || [])
                .filter(
                    (filter) => filter.type !== "all" && filter.value && filter.active,
                )
                .map((filter) => filter.value);
        }
        if (!attendeeIds.includes(user.partnerId)) {
            attendeeIds.push(user.partnerId);
        }
        return this.orm.call("res.partner", "get_worklocation", [
            attendeeIds,
            serializeDateTime(data.range.start),
            serializeDateTime(data.range.end),
        ]);
    },

    async loadWorkLocations(data) {
        const res = await this.fetchEventLocation(data);
        this.multiCalendar =
            Object.keys(res).length > 1 ||
            Object.values(res).some((location) => location.user_id !== user.userId);
        const filters = data.filterSections.partner_ids?.filters;
        data.userFilterActive =
            filters &&
            (filters.filter((filter) => filter.value === user.partnerId)[0]?.active ||
                (filters[filters.length - 1].type === "all" &&
                    filters[filters.length - 1].active));
        const events = {};
        let previousDay;
        const rangeStart = data.range.start.startOfDay();
        const rangeEnd = endOf(data.range.end, "day");
        const days = [];
        for (
            let index = 0, day = rangeStart;
            compareDates(day, rangeEnd) < 0;
            day = rangeStart.add({ days: ++index })
        ) {
            days.push(day);
        }
        for (const startDay of days) {
            const dayISO = toISODate(startDay);
            const dayName = WEEKDAY_NAMES[startDay.dayOfWeek - 1];
            for (const employeeId in res) {
                const employee = res[employeeId];
                const hasException =
                    employee.exceptions && dayISO in employee.exceptions;
                const workLocationData = hasException
                    ? employee.exceptions[dayISO]
                    : employee[`${dayName}_location_id`];
                if (this.multiCalendar) {
                    events[dayISO] ??= {};
                    const locationType = workLocationData?.location_type;
                    if (!locationType) {
                        continue;
                    }
                    events[dayISO][locationType] ??= [];
                    events[dayISO][locationType].push(
                        this.createHomeworkingRecordAt(
                            employee,
                            startDay,
                            workLocationData,
                        ),
                    );
                } else {
                    const currentEvent = this.createHomeworkingRecordAt(
                        employee,
                        startDay,
                        workLocationData,
                    );
                    const previousEvent = events[previousDay];
                    if (
                        previousEvent &&
                        previousEvent.icon === currentEvent.icon &&
                        previousEvent.title === currentEvent.title
                    ) {
                        previousEvent.end = previousEvent.end.add({ days: 1 });
                        currentEvent.display = false;
                    } else {
                        previousDay = dayISO;
                    }
                    if (currentEvent.title) {
                        events[dayISO] = currentEvent;
                    }
                }
            }
        }
        return events;
    },

    createHomeworkingRecordAt(record, day, workLocationData) {
        const {
            location_type,
            location_name,
            work_location_id,
            hr_employee_location_id,
        } = workLocationData;
        const ghostRecord = !hr_employee_location_id;
        const id = ghostRecord
            ? `default-location-${record.employee_id}-${day.epochMilliseconds}`
            : String(hr_employee_location_id);
        return {
            id,
            title: location_name,
            start: day,
            end: day.add({ days: 1 }),
            display: true,
            multiCalendar: this.multiCalendar,
            homeworking: true,
            employeeId: record.employee_id,
            employeeName: record.employee_name,
            icon: location_type,
            userId: record.user_id,
            partnerId: record.partner_id,
            colorIndex: this.partnerColorMap[record.partner_id],
            resModel: "hr.employee.location",
            work_location_id,
            ghostRecord,
            rawRecord: record,
        };
    },

    get worklocations() {
        return this.data.worklocations;
    },

    mapPartnersToColor(data) {
        return (data.filterSections.partner_ids?.filters || [])
            .filter((filter) => filter.type !== "all" && filter.value)
            .reduce(
                (map, partner) => ({
                    ...map,
                    [partner.value]: getColor(partner.colorIndex),
                }),
                {},
            );
    },

    /** @override */
    async updateData(data) {
        await super.updateData(...arguments);
        this.partnerColorMap = this.mapPartnersToColor(data);
        data.worklocations = await this.loadWorkLocations(data);
    },
});
