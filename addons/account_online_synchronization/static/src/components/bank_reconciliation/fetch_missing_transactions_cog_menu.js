/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { COG_GROUP } from "@web/search/cog_menu/cog_menu_group";
import { CogMenuItem } from "@web/search/cog_menu/cog_menu_item";
import { useSearchModel } from "@web/search/search_model";

import { isBankReconciliationView } from "./find_duplicate_transactions_cog_menu.js";

const cogMenuRegistry = registry.category("cogMenu");

/**
 * 'Fetch Missing Transactions' cog menu item of the bank reconciliation widget.
 *
 * Opens a wizard to fetch missing/pending transactions since a given date. The server
 * preselects the journal when a single one is active, otherwise it asks the user.
 * @extends Component
 */
export class FetchMissingTransactions extends Component {
    static template = "account_online_synchronization.FetchMissingTransactions";
    static components = { CogMenuItem };
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.searchModel = useSearchModel();
        this.orm = useService("orm");
        this.action = useService("action");
    }

    async openFetchMissingTransactionsWizard() {
        const { context } = this.searchModel;
        const activeModel = context.active_model;
        let activeIds = [];
        if (activeModel === "account.journal") {
            activeIds = context.active_ids;
        } else if (context.default_journal_id) {
            activeIds = context.default_journal_id;
        }
        const action = await this.orm.call(
            "account.journal",
            "action_view_missing_transaction_wizard",
            [activeIds],
        );
        return this.action.doAction(action);
    }
}

export const fetchMissingTransactionItem = {
    Component: FetchMissingTransactions,
    groupNumber: COG_GROUP.APP,
    isDisplayed: isBankReconciliationView,
};

cogMenuRegistry.add("fetch-missing-transaction-menu", fetchMissingTransactionItem, {
    sequence: 10,
});
