/** @odoo-module native */
import { serializeDate } from "@web/core/l10n/dates";
import { useService } from "@web/core/utils/hooks";

export function useWorkEntryPayslip({ getEmployeeIds, getRange }) {
    const action = useService("action");
    const orm = useService("orm");
    return async () => {
        const { start, end } = getRange();
        const ids = await orm.create("hr.payslip.run", [
            {
                date_start: serializeDate(start),
                date_end: serializeDate(end),
            },
        ]);
        try {
            await orm.call("hr.payslip.run", "generate_payslips", [ids], {
                employee_ids: getEmployeeIds(),
            });
        } catch (error) {
            await orm.call("hr.payslip.run", "unlink", [ids]);
            throw error;
        }
        await action.doAction(
            await orm.call("hr.payslip.run", "action_view_payslips", [ids]),
        );
    };
}
