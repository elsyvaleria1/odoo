/** @odoo-module native */

import { PlanningCalendarFront } from "@planning/interactions/planning_calendar_front";
import { patch } from "@web/core/utils/patch";

function setFieldVisibility(el, visible) {
    el.style.display = visible ? "" : "none";
    if (el.previousElementSibling) {
        el.previousElementSibling.style.display = visible ? "" : "none";
    }
}

patch(PlanningCalendarFront.prototype, {
    eventFunction(calEvent) {
        super.eventFunction(calEvent);
        const projectEl = document.getElementById("project");
        setFieldVisibility(projectEl, !!calEvent.event.extendedProps.project);
        if (calEvent.event.extendedProps.project) {
            projectEl.textContent = calEvent.event.extendedProps.project;
        }
    },
});
