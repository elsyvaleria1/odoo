/** @odoo-module native */
import { BaseImportModel } from "@base_import/import_model";
import { proxy } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class BankStatementCSVImportModel extends BaseImportModel {
    async init() {
        this.importOptionsValues.bank_stmt_import = {
            value: true,
        };
        return Promise.resolve();
    }
}

/**
 * @returns {BankStatementCSVImportModel}
 */
export function useBankStatementCSVImportModel({ env, context }) {
    const orm = useService("orm");
    return proxy(new BankStatementCSVImportModel({ env, context, orm }));
}
