/** @odoo-module native */
import { BankRecKanbanRenderer } from "@account/components/bank_reconciliation/kanban_renderer";
import { patch } from "@web/core/utils/patch";

patch(BankRecKanbanRenderer.prototype, {
    async getJournalTotalAmount() {
        const values = await super.getJournalTotalAmount();
        this.globalState.journalAvailableBalanceAmount =
            values.available_balance_amount || "";
    },
});
