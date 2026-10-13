/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { RemainingDaysField } from "@web/fields/temporal/remaining_days/remaining_days_field";

export class AppraisalDeadlineDate extends RemainingDaysField {
    /** @override */
    get diffDays() {
        const result = super.diffDays;
        const state = this.props.record.data.state;
        if (result != null && state === "3_done") {
            return 1;
        }
        return result;
    }

    /** @override */
    get diffString() {
        return this.formattedValue;
    }
}

export const appraisalDeadlineDate = {
    component: AppraisalDeadlineDate,
    displayName: _t("Appraisal Deadline"),
    supportedTypes: ["date", "datetime"],
};

registry.category("fields").add("appraisal_deadline_date", appraisalDeadlineDate);
