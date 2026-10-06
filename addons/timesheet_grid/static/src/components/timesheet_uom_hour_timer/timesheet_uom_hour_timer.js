/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

import { TimesheetDisplayTimer } from "../timesheet_display_timer/timesheet_display_timer.js";

export class TimesheetUOMHourTimer extends Component {
    static components = { TimesheetDisplayTimer };
    static template = "timesheet_grid.TimesheetUOMHourTimer";
    static props = { ...standardFieldProps, context: t.object().optional() };
    props = useProps(this.constructor.props);

    setup() {
        this.ormService = useService("orm");
        this.timesheetTimerService = useService("timesheet_timer");
        this.state = proxy(this.timesheetTimerService.timerState);
    }

    get displayButton() {
        return this.props.record.data.display_timer && this.props.readonly;
    }

    get iconClass() {
        const icon = this.addTimeMode ? "plus" : this.isTimerRunning ? "stop" : "play";
        const textColor = this.isTimerRunning ? "danger" : "primary";
        return `fa-solid fa-${icon} text-${textColor}`;
    }

    get isTimerRunning() {
        return this.props.record.data.is_timer_running;
    }

    get addTimeMode() {
        return this.state.addTimeMode;
    }

    get title() {
        return this.isTimerRunning ? _t("Stop") : _t("Start");
    }

    async onClick(ev) {
        ev.preventDefault();
        const action = this.addTimeMode
            ? "increase"
            : this.isTimerRunning
              ? "stop"
              : "start";
        if (action === "start") {
            await this.timesheetTimerService.startTimer(
                { id: this.props.record.resId },
                true,
            );
        } else if (action === "stop") {
            await this.timesheetTimerService.stopTimer([], {}, true);
        } else {
            await this.ormService.call(
                this.props.record.resModel,
                `action_timer_${action}`,
                [[this.props.record.resId]],
                { context: this.props.context },
            );
            await this.props.record.model.load();
        }
    }
}

export const timesheetUOMHourTimer = {
    component: TimesheetUOMHourTimer,
    extractProps(fieldInfo, dynamicInfo) {
        return {
            context: dynamicInfo.context,
        };
    },
    fieldDependencies: [
        { name: "display_timer", type: "boolean" },
        { name: "is_timer_running", type: "boolean" },
    ],
};

registry.category("fields").add("timesheet_uom_hour_timer", timesheetUOMHourTimer);
