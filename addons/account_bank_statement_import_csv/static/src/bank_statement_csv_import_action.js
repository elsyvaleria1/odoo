/** @odoo-module native */
import { ImportAction } from "@base_import/import_action/import_action";
import { onWillStart } from "@odoo/owl";
import { x2ManyCommands } from "@web/core/network";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";

import { useBankStatementCSVImportModel } from "./bank_statement_csv_import_model.js";

export class BankStatementImportAction extends ImportAction {
    setup() {
        super.setup();
        this.config = useViewConfig();

        this.orm = useService("orm");

        this.model = useBankStatementCSVImportModel({
            env: this.appContext,
            context: this.props.action.params.context || {},
        });

        this.config.setDisplayName(_t("Import Bank Statement"));
        this.state.filename = this.props.action.params.filename || undefined;

        onWillStart(async () => {
            if (this.props.action.params.context) {
                this.model.id = this.props.action.params.context.wizard_id;
                await this.model.init();
                await super.handleFilesUpload([{ name: this.state.filename }]);
            }
        });
    }

    async openRecords(resIds) {
        const statementLines = await this.orm.searchRead(
            "account.bank.statement.line",
            [["id", "in", resIds]],
            ["statement_id", "journal_id"],
        );
        const statementIds = Array.from(
            new Set(
                statementLines
                    .filter((statementLine) => statementLine.statement_id)
                    .map((statementLine) => statementLine.statement_id[0]),
            ),
        );
        if (statementIds.length) {
            await this.orm.write("account.bank.statement", statementIds, {
                attachment_ids: this.props.action.params.context.attachment_ids.map(
                    (attachment) => x2ManyCommands.link(attachment),
                ),
            });
        }
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            name: _t("Imported records"),
            res_model: "account.bank.statement.line",
            view_mode: "kanban,list",
            views: [
                [false, "kanban"],
                [false, "list"],
            ],
            target: "current",
            path: "imported-records",
            context: {
                search_default_imported_statement_lines: 1,
                search_default_journal_id: statementLines[0].journal_id[0],
                imported_transaction_ids: resIds,
            },
        });
    }
}

registry.category("actions").add("import_bank_stmt", BankStatementImportAction);
