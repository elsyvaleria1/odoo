/** @odoo-module native */
import { BaseImportModel } from "@base_import/import_model";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";

patch(BaseImportModel.prototype, {
    async init() {
        await super.init(...arguments);

        if (this.resModel === "account.bank.statement") {
            this.importTemplates.push({
                label: _t("Import Template for Bank Statements"),
                template:
                    "/account_bank_statement_import/static/csv/account.bank.statement.csv",
            });
        }
    },
});
