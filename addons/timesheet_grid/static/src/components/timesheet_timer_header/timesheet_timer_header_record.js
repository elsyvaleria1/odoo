/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { evaluateBooleanExpr } from "@web/core/py_js/py";
import { useService } from "@web/core/utils/hooks";
import { Field } from "@web/fields/field";

import { TimesheetDisplayTimer } from "../timesheet_display_timer/timesheet_display_timer.js";

export class TimesheetTimerHeaderRecord extends Component {
    static template = "timesheet_grid.TimesheetTimerHeaderRecord";
    static components = {
        Field,
        TimesheetDisplayTimer,
    };
    static props = {
        timesheet: t.object(),
        fields: t.object().optional({}),
        stopTimer: t.function().optional(() => () => {}),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.evaluateBooleanExpr = evaluateBooleanExpr;
        this.timerService = useService("timesheet_timer");
    }

    get fieldNamePerSequence() {
        return {
            1: "name",
            10: "project_id",
            20: "task_id",
        };
    }

    get activeFieldNames() {
        return Object.values(this.fieldNamePerSequence);
    }

    getFieldInfo(fieldName) {
        return {
            isVisible: "True",
            ...(this.props.fields[fieldName] ||
                this.timerService.getTimesheetTimerFieldInfo(fieldName)),
        };
    }

    async _onKeyDown(ev) {
        if (ev.key === "Enter") {
            if (this.props.stopTimer) {
                await this.props.stopTimer();
            } else {
                this.timerService.stopTimer();
            }
        }
    }
}
