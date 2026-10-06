/** @odoo-module native */
import { CalendarYearRenderer } from "@web/views/calendar";

import { CalendarWithRecurrenceYearPopover } from "./calendar_with_recurrence_year_popover.js";

export class CalendarWithRecurrenceYearRenderer extends CalendarYearRenderer {
    static components = {
        ...CalendarYearRenderer.components,
        Popover: CalendarWithRecurrenceYearPopover,
    };
}
