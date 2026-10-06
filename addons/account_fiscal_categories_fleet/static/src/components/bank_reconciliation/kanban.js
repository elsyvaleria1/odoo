/** @odoo-module native */
import { BankRecKanbanController } from "@account/components/bank_reconciliation/kanban_controller";
import { patch } from "@web/core/utils/patch";

patch(BankRecKanbanController.prototype, {
    getBankRecLineInvalidFields(line) {
        const invalidFields = super.getBankRecLineInvalidFields(...arguments);
        if (line.data.need_asset && !line.data.asset_id) {
            invalidFields.push("vehicle");
        }
        return invalidFields;
    },
});
