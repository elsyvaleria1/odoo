/** @odoo-module native */

import { PlanningCalendarFront } from "@planning/interactions/planning_calendar_front";
import { patch } from "@web/core/utils/patch";

patch(PlanningCalendarFront.prototype, {
    // override popup of calendar
    eventFunction(calEvent) {
        super.eventFunction(calEvent);
        const saleLineEl = document.getElementById("sale_line");
        if (calEvent.event.extendedProps.sale_line) {
            saleLineEl.textContent = calEvent.event.extendedProps.sale_line;
            saleLineEl.style.display = "";
            saleLineEl.previousElementSibling.style.display = "";
        } else {
            saleLineEl.style.display = "none";
            saleLineEl.previousElementSibling.style.display = "none";
        }
    },
});
