/** @odoo-module native */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { RemainingDaysField } from "@web/fields/temporal/remaining_days/remaining_days_field";

/**
 * The appraisal deadline, shown as a date and coloured by urgency.
 *
 * It subclasses RemainingDaysField for the colouring only: `diffString`
 * deliberately returns the formatted date rather than "in 3 days", so the
 * widget must not be called `appraisal_remaining_days` - it never showed
 * remaining days.
 */
export class AppraisalDeadlineDate extends RemainingDaysField {
    /** @override - a done appraisal is never urgent, whatever its date. */
    get diffDays() {
        const result = super.diffDays;
        const state = this.props.record.data.state;
        if (result != null && state === "3_done") {
            // A positive value the colouring reads as "not late"; the number
            // itself is never displayed, because diffString overrides it.
            return 1;
        }
        return result;
    }

    /** @override - show the date itself, not a relative span. */
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
