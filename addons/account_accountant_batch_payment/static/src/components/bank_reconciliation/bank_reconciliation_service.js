/** @odoo-module native */
import { BankReconciliationService } from "@account/components/bank_reconciliation/bank_reconciliation_service";
import { proxy } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";

patch(BankReconciliationService.prototype, {
    setup(env, services) {
        super.setup(env, services);
        this.hasAvailableBatchPayments = proxy({ value: false });
    },

    async updateHasAvailableBatchPayments(journalId) {
        this.hasAvailableBatchPayments.value = !!(await this.orm.searchCount(
            "account.batch.payment",
            [
                ["state", "!=", "reconciled"],
                ["journal_id", "=", journalId],
            ],
            {
                limit: 1,
            },
        ));
    },
});
