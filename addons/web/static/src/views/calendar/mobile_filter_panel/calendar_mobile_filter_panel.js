// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { getColor, sortCalendarFilters } from "@web/views/calendar/calendar_utils";

export class CalendarMobileFilterPanel extends Component {
    static components = {};
    static template = "web.CalendarMobileFilterPanel";
    static props = {
        model: t.object(),
        sideBarShown: t.boolean(),
        toggleSideBar: t.function(),
    };
    props = useProps(this.constructor.props);
    /** @returns {"down" | "left"} */
    get caretDirection() {
        return this.props.sideBarShown ? "down" : "left";
    }
    /**
     * @param {{ colorIndex: number }} filter
     * @returns {string}
     */
    getFilterColor(filter) {
        return `o_color_${getColor(filter.colorIndex)}`;
    }
    /**
     * @param {{ filters: Array<{ type: string, value: any, label: string }> }} section
     * @returns {any[]}
     */
    getSortedFilters(section) {
        return sortCalendarFilters(section.filters, ["user", "record", "dynamic"]);
    }
}
