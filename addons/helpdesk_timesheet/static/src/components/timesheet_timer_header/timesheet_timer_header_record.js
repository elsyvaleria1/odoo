/** @odoo-module native */
import { TimesheetTimerHeaderRecord } from "@timesheet_grid/components/timesheet_timer_header/timesheet_timer_header_record";
import { patch } from "@web/core/utils/patch";

patch(TimesheetTimerHeaderRecord.prototype, {
    get fieldNamePerSequence() {
        return {
            ...super.fieldNamePerSequence,
            30: "helpdesk_ticket_id",
        };
    },

    getFieldInfo(fieldName) {
        const fieldInfo = super.getFieldInfo(fieldName);
        if (fieldName === "task_id") {
            if (this.props.timesheet) {
                fieldInfo.isVisible = !this.evaluateBooleanExpr(
                    "has_helpdesk_team and not task_id",
                    this.props.timesheet.evalContextWithVirtualIds,
                );
            }
        } else if (fieldName === "helpdesk_ticket_id") {
            if (this.props.timesheet) {
                fieldInfo.isVisible = !this.evaluateBooleanExpr(
                    "not has_helpdesk_team and not helpdesk_ticket_id",
                    this.props.timesheet.evalContextWithVirtualIds,
                );
                // TODO: check if it is still needed
                fieldInfo.context = `{'default_project_id': project_id}`;
            }
        }
        return fieldInfo;
    },
});
