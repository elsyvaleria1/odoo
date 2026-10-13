/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { COG_GROUP, isActWindowView } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";
import { useSearchModel } from "@web/search/search_model";

export function isBankReconciliationView(env) {
    return (
        !env.isSmall &&
        isActWindowView(env, ["kanban", "list"]) &&
        ["bank_rec_widget_kanban", "bank_rec_list"].includes(env.config.viewSubType)
    );
}

/** @extends Component */
export class FindDuplicateTransactions extends Component {
    static template = "account_online_synchronization.FindDuplicateTransactions";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.searchModel = useSearchModel();
        this.action = useService("action");
    }

    async openFindDuplicateTransactionsWizard() {
        const { context } = this.searchModel;
        const activeModel = context.active_model;
        let activeIds = [];
        if (activeModel === "account.journal") {
            activeIds = context.active_ids;
        } else if (context.default_journal_id) {
            activeIds = context.default_journal_id;
        }
        return this.action.doActionButton({
            type: "object",
            resModel: "account.journal",
            name: "action_view_duplicate_transaction_wizard",
            resIds: activeIds,
        });
    }
}

export const findDuplicateTransactionItem = {
    Component: FindDuplicateTransactions,
    groupNumber: COG_GROUP.APP,
    isDisplayed: isBankReconciliationView,
};

registry
    .category("cogMenu")
    .add("find-duplicate-transaction-menu", findDuplicateTransactionItem, {
        sequence: 20,
    });
