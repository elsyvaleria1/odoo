/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus, useMountedListener, useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";

export class TimesheetTimerHeaderButtons extends Component {
    static template = "timesheet_grid.TimesheetTimerHeaderButtons";
    static props = {
        startTimer: t.function().optional(),
        stopTimer: t.function().optional(),
        deleteTimer: t.function().optional(),
        timerRunning: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.resModel = "account.analytic.line";
        this.timerService = useService("timesheet_timer");
        this.timerReactive = proxy(this.timerService.timer);
        this.startButton = elementRef();
        this.stopButton = elementRef();
        useAutofocus({ ref: this.startButton });
        useAutofocus({ ref: this.stopButton });
        this.onClickTimerButton = useDebounced(
            this.handleClickTimerButton.bind(this),
            250,
        );
        useMountedListener(document.body, "click", (ev) => {
            if (
                ev.target.closest(".modal, .popover") ||
                ["input", "textarea"].includes(ev.target.tagName.toLowerCase())
            ) {
                return;
            }
            (this.startButton.el ?? this.stopButton.el)?.focus();
        });
    }

    async handleClickTimerButton() {
        if (this.props.timerRunning) {
            this._onClickStopTimer();
        } else {
            this._onClickStartTimer();
        }
    }

    async _onClickStartTimer() {
        if (this.props.startTimer) {
            this.props.startTimer();
        } else {
            this.timerService.startTimer();
        }
    }

    async _onClickStopTimer() {
        if (this.props.stopTimer) {
            await this.props.stopTimer();
        } else {
            await this.timerService.stopTimer();
        }
    }

    async _onClickDeleteTimer() {
        if (this.props.deleteTimer) {
            this.props.deleteTimer();
        } else {
            this.timerService.deleteTimer();
        }
    }
}
