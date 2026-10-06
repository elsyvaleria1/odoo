/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { TimesheetTimerHeaderButtons } from "./timesheet_timer_header_buttons.js";
import { TimesheetTimerHeaderRecord } from "./timesheet_timer_header_record.js";

export class TimesheetTimerHeader extends Component {
    static template = "timesheet_grid.TimesheetTimerHeader";
    static components = {
        TimesheetTimerHeaderButtons,
        TimesheetTimerHeaderRecord,
    };
    static props = {
        slots: t.object().optional(),
        timesheet: t.object().optional(),
        fields: t.object().optional(),
        onTimerStarted: t.function(),
        onTimerStopped: t.function(),
        onTimerUnlinked: t.function(),
        onClick: t.function().optional(() => function () {}),
        className: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.timerService = useService("timesheet_timer");
        this.timerState = proxy(this.timerService.timerState);
    }

    get classNames() {
        const displayFlex = this.isMobile && !this.timerState.isRunning;
        const classNames = {
            "d-flex": displayFlex,
            "d-grid": !displayFlex,
        };
        if (this.props.className) {
            classNames[this.props.className] = true;
        }
        return classNames;
    }

    get isMobile() {
        return this.ui.isSmall;
    }

    async stopTimer(ev) {
        if (await this.props.timesheet.save()) {
            this.props.onTimerStopped();
        }
    }
}
