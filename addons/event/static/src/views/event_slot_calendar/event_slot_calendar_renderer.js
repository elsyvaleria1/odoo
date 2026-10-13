/** @odoo-module native */
import { fromJSDate, toISODate } from "@web/core/l10n/dates";
import {
    CalendarCommonRenderer,
    CalendarRenderer,
    CalendarYearRenderer,
} from "@web/views/calendar";

export class EventSlotCalendarCommonRenderer extends CalendarCommonRenderer {
    static eventTemplate = "event.EventSlotCalendarCommonRenderer.event";
    static cellIsSelectable = (cell) => !cell.classList.contains("o_calendar_disabled");

    setup() {
        super.setup(...arguments);
        this.rangeStartDate =
            this.props.model.meta.context.event_calendar_range_start_date;
        this.rangeEndDate = this.props.model.meta.context.event_calendar_range_end_date;
    }

    getDayCellClassNames(info) {
        const date = toISODate(fromJSDate(info.date));
        if (
            this.rangeStartDate &&
            this.rangeEndDate &&
            (date < this.rangeStartDate || date > this.rangeEndDate)
        ) {
            return ["o_calendar_disabled"];
        }
        return [];
    }

    /** @override */
    isSelectionAllowed() {
        return false;
    }

    /** @override */
    onDateClick(info) {
        if (info.dayEl.classList.contains("o_calendar_disabled")) {
            return;
        }
        return super.onDateClick(info);
    }
}

export class EventSlotCalendarRenderer extends CalendarRenderer {
    static components = {
        ...CalendarRenderer.components,
        day: EventSlotCalendarCommonRenderer,
        week: EventSlotCalendarCommonRenderer,
        month: EventSlotCalendarCommonRenderer,
        year: CalendarYearRenderer,
    };
}
