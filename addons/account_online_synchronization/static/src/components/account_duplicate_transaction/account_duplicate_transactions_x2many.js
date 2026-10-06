/** @odoo-module native */
import { onMounted } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { registry } from "@web/core/registry";
import { X2ManyField, x2ManyField } from "@web/fields/relational/x2many";
import { useViewModel } from "@web/model/model";
import { ListRenderer } from "@web/views/list";

import { useCheckDuplicateService } from "./account_duplicate_transaction_hook.js";

export class AccountDuplicateTransactionsListRenderer extends ListRenderer {
    static template =
        "account_online_synchronization.AccountDuplicateTransactionsListRenderer";
    static recordRowTemplate =
        "account_online_synchronization.AccountDuplicateTransactionsRecordRow";

    setup() {
        super.setup();
        this.debug = useDebugMode();
        this.model = useViewModel();
        this.duplicateCheckService = useCheckDuplicateService();

        onMounted(() => {
            this.deleteButton = document.querySelector(
                'button[name="delete_selected_transactions"]',
            );
            this.deleteButton.disabled = true;
        });
    }

    toggleRecordSelection(selected, record) {
        this.duplicateCheckService.updateLIne(selected, record.data.id);
        this.deleteButton.disabled =
            this.duplicateCheckService.selectedLines.size === 0;
    }

    get hasSelectors() {
        return true;
    }

    getRowClass(record) {
        let classes = super.getRowClass(record);
        const firstIdsInGroup = this.model.root.data.first_ids_in_group;
        if (
            firstIdsInGroup instanceof Array &&
            firstIdsInGroup.includes(record.data.id)
        ) {
            classes += " account_duplicate_transactions_lines_list_x2many_group_line";
        }
        return classes;
    }
}

export class AccountDuplicateTransactionsLinesListX2ManyField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: AccountDuplicateTransactionsListRenderer,
    };
}

registry.category("fields").add("account_duplicate_transactions_lines_list_x2many", {
    ...x2ManyField,
    component: AccountDuplicateTransactionsLinesListX2ManyField,
});
