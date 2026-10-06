/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";

const numberRange = (min, max) => [...Array(max - min)].map((_, i) => i + min);

const HOURS = numberRange(0, 24).map((hour) => [hour, String(hour)]);
const MINUTES = numberRange(0, 60).map((minute) => [
    minute,
    String(minute || 0).padStart(2, "0"),
]);

export class FloatTimeSelectionPopover extends Component {
    static props = {
        close: t.function(),
        onTimeChange: t.function(),
        timeValues: t.object({
            hours: t.string(),
            minutes: t.string(),
            floatValue: t.number(),
        }),
    };

    static template = "hr_holidays.FloatTimeSelectionPopover";
    props = useProps(this.constructor.props);

    setup() {
        this.availableHours = HOURS;
        this.availableMinutes = MINUTES;
        this.state = proxy({
            selectedHours: this.props.timeValues.hours,
            selectedMinutes: this.props.timeValues.minutes,
        });
    }

    onTimeChange() {
        this.props.onTimeChange({
            hours: this.state.selectedHours,
            minutes: this.state.selectedMinutes,
        });
    }
}
