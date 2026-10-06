/** @odoo-module native */
import { WorkEntryCalendarMultiSelectionButtons } from "@hr_work_entry/views/work_entry_calendar/work_entry_multi_selection_buttons";
import { t } from "@odoo/owl";

export class WorkEntriesMultiSelectionButtons extends WorkEntryCalendarMultiSelectionButtons {
    static template = "hr_work_entry_enterprise.WorkEntriesMultiSelectionButtons";
    static props = {
        reactive: t.object({
            ...WorkEntryCalendarMultiSelectionButtons.props.reactive.toShape(),
            onPlan: t.function().optional(),
        }),
    };
    /**
     * @override
     */
    makeValues(workEntryTypeId) {
        const values = super.makeValues(workEntryTypeId);
        delete values.employee_id;
        return values;
    }
}
