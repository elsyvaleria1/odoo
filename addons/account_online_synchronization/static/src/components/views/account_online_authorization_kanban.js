/** @odoo-module native */
import { BankRecKanbanController } from "@account/components/bank_reconciliation/kanban_controller";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { useSearchModel } from "@web/search/search_model";

patch(BankRecKanbanController.prototype, {
    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        this.action = useService("action");
        this.displayDuplicateWarning = !!this.props.context.duplicates_from_date;
    },

    async onWarningClick() {
        const { context } = this.searchModel;
        return this.action.doActionButton({
            type: "object",
            resModel: "account.journal",
            name: "action_view_duplicate_transaction_wizard",
            resId: context.default_journal_id || context.active_id,
            args: JSON.stringify([context.duplicates_from_date]),
        });
    },
});
