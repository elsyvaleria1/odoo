/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { weekdayNames } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";

export class LocationSchedule extends Component {
    static template = "delivery.locationSelector.schedule";
    static props = {
        openingHours: t.record(t.array(t.string()).optional()),
        wrapClass: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    /**
     * @param {Number} weekday
     * @return {Object}
     */
    getWeekDay(weekday) {
        const dayName = weekdayNames()[weekday];
        return dayName.charAt(0).toUpperCase() + dayName.slice(1);
    }

    get closedLabel() {
        return _t("Closed");
    }
}
