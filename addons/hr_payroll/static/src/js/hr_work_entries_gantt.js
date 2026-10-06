/** @odoo-module native */
import { useWorkEntryPayslip } from "@hr_payroll/views/work_entry_calendar/work_entry_calendar_hook";
import { WorkEntriesGanttController } from "@hr_work_entry_enterprise/work_entries_gantt_controller";
import { patch } from "@web/core/utils/patch";

patch(WorkEntriesGanttController.prototype, {
    setup() {
        super.setup(...arguments);
        this.onGeneratePayslips = useWorkEntryPayslip({
            getEmployeeIds: () => this.getActiveEmployeeIds(),
            getRange: () => this.model.getRange(),
        });
    },

    checkConflicts() {
        return this.model.data.records.some((record) => record.state === "conflict");
    },

    getActiveEmployeeIds() {
        const employeeIds = new Set();
        for (const rec of this.model.data.records) {
            if (rec.employee_id) {
                employeeIds.add(rec.employee_id.id);
            }
        }
        return [...employeeIds];
    },

    getShowGeneratePayslipsButton() {
        return this.model.data.records.some((record) => record.state !== "validated");
    },
});
