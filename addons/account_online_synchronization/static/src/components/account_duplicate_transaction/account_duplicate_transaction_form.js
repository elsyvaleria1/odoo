/** @odoo-module native */
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController, formView } from "@web/views/form";

import { useCheckDuplicateService } from "./account_duplicate_transaction_hook.js";

export class AccountDuplicateTransactionsFormController extends FormController {
    setup() {
        super.setup();
        this.action = useService("action");
        this.duplicateCheckService = useCheckDuplicateService();
    }

    async beforeExecuteActionButton(clickParams) {
        if (clickParams.name === "delete_selected_transactions") {
            const selected = this.duplicateCheckService.selectedLines;
            if (selected.size) {
                await this.orm.call("account.bank.statement.line", "unlink", [
                    Array.from(selected),
                ]);
                this.action.doAction({
                    type: "ir.actions.client",
                    tag: "reload",
                });
            }
            return false;
        }
        return super.beforeExecuteActionButton(...arguments);
    }

    get cogMenuProps() {
        const props = super.cogMenuProps;
        props.items.action = [];
        return props;
    }
}

export const form = {
    ...formView,
    Controller: AccountDuplicateTransactionsFormController,
};

registry.category("views").add("account_duplicate_transactions_form", form);
