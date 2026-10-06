// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { DateTimePicker } from "@web/components/datetime/datetime_picker";
import { getStartOfLocalWeek, hasSame, toDate, toDateTime } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";
import { CalendarFilterSection } from "@web/views/calendar/calendar_filter_section/calendar_filter_section";

export class CalendarSidePanel extends Component {
    static components = {
        DatePicker: DateTimePicker,
        FilterSection: CalendarFilterSection,
    };
    static template = "web.CalendarSidePanel";
    static props = { model: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.ui = useService("ui");
    }

    /** @returns {Object} */
    get datePickerProps() {
        return {
            type: "date",
            showWeekNumbers: false,
            maxPrecision: "days",
            daysOfWeekFormat: "narrow",
            onSelect: (
                /** @type {import("@web/core/l10n/dates").NullableDate} */ date,
            ) => {
                if (!date) {
                    return;
                }
                const current = toDate(this.props.model.date);
                let scale = "week";

                if (hasSame(current, date, "day")) {
                    const scales = ["month", "week", "day"];
                    scale =
                        scales[
                            (scales.indexOf(this.props.model.scale) + 1) % scales.length
                        ];
                } else {
                    const currentWeekStart = getStartOfLocalWeek(current);
                    const pickedWeekStart = getStartOfLocalWeek(date);
                    if (hasSame(currentWeekStart, pickedWeekStart, "day")) {
                        scale = "day";
                    }
                }

                this.props.model.load({ scale, date: toDateTime(date) });
            },
            value: toDate(this.props.model.date),
        };
    }
    /** @returns {{ model: Object }} */
    get filterPanelProps() {
        return {
            model: this.props.model,
        };
    }

    /** @returns {boolean} */
    get showDatePicker() {
        return this.props.model.showDatePicker && !this.ui.isSmall;
    }
}
