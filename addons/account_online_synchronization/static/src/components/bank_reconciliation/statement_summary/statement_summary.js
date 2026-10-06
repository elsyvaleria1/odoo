/** @odoo-module native */
import {
    BankRecStatementSummary,
    bankRecStatementSummaryProps,
} from "@account/components/bank_reconciliation/statement_summary/statement_summary";
import { t } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";

Object.assign(bankRecStatementSummaryProps, {
    journalAvailableBalanceAmount: t.string().optional(),
});

patch(BankRecStatementSummary.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    },

    async actionOpenPendingBankStatementLines() {
        this.action.doActionButton({
            type: "object",
            resId: this.props.journalId,
            name: "action_view_pending_bank_statement_lines",
            resModel: "account.journal",
        });
    },
});
