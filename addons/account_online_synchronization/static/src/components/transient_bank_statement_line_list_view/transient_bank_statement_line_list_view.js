/** @odoo-module native */
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSearchModel } from "@web/search/search_model";
import { ListController, ListRenderer, listView } from "@web/views/list";

export class TransientBankStatementLineListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async onClickImportTransactions() {
        const resIds = await this.model.root.getResIds(true);
        const resultAction = await this.orm.call(
            "account.online.transaction.preview",
            "action_import_transactions",
            [resIds],
        );
        this.action.doAction(resultAction);
    }

    get allowImportTransaction() {
        return !this.props.context.disable_import;
    }
}

export class TransientBankStatementLineListRenderer extends ListRenderer {
    static template =
        "account_online_synchronization.TransientBankStatementLineRenderer";

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.searchModel = useSearchModel();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async openManualEntries() {
        if (
            this.searchModel.context.active_model ===
                "wizard.account.journal.preview.missing.transaction" &&
            this.searchModel.context.active_ids
        ) {
            const activeIds = this.searchModel.context.active_ids;
            const action = await this.orm.call(
                "wizard.account.journal.preview.missing.transaction",
                "action_view_manual_bank_statement_lines",
                activeIds,
            );
            this.action.doAction(action);
        }
    }

    async openCancelledEntries() {
        if (
            this.searchModel.context.active_model ===
                "wizard.account.journal.preview.missing.transaction" &&
            this.searchModel.context.active_ids
        ) {
            return await this.action.doActionButton({
                name: "action_view_cancelled_bank_statement_lines",
                type: "object",
                resModel: "wizard.account.journal.preview.missing.transaction",
                resIds: this.searchModel.context.active_ids,
            });
        }
    }
}

export const TransientBankStatementLineListView = {
    ...listView,
    Renderer: TransientBankStatementLineListRenderer,
    Controller: TransientBankStatementLineListController,
    buttonTemplate: "TransientBankStatementLineButtonTemplate",
};

registry
    .category("views")
    .add("transient_bank_statement_line_list_view", TransientBankStatementLineListView);
