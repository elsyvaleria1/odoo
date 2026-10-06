/** @odoo-module native */
import { useService } from "@web/core/utils/hooks";
import { CalendarSidePanel } from "@web/views/calendar";

import { PlanningCalendarFilterSection } from "../planning_filter_section/planning_calendar_filter_section.js";

export class PlanningCalendarSidePanel extends CalendarSidePanel {
    static template = "planning.PlanningCalendarSidePanel";
    static components = {
        ...CalendarSidePanel.components,
        FilterSection: PlanningCalendarFilterSection,
    };

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    // overwrite to allow the display of the datepicker when a mode other than 'filter' was selected in the month scale
    get showDatePicker() {
        return (
            this.props.model.showDatePicker &&
            !this.ui.isSmall &&
            (this.props.model.meta.scale !== "month" || this.props.mode === "FILTER")
        );
    }
}
