/** @odoo-module native */
import { BankRecKanbanRenderer } from "@account/components/bank_reconciliation/kanban_renderer";
import { onWillStart } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";

patch(BankRecKanbanRenderer.prototype, {
    setup() {
        super.setup();

        onWillStart(async () => {
            await this.bankReconciliation.updateHasAvailableBatchPayments(
                this.globalState.journalId,
            );
        });
    },
});
