/** @odoo-module native */
import { provideSpreadsheetEnv } from "@spreadsheet/hooks";
import { AbstractSpreadsheetAction } from "@spreadsheet_edition/bundle/actions/abstract_spreadsheet_action";
import { registry } from "@web/core/registry";

export class SpreadsheetTestAction extends AbstractSpreadsheetAction {
    static template = "test_spreadsheet_edition.SpreadsheetTestAction";
    resModel = "spreadsheet.test";
    threadField = "dummy_id";

    setup() {
        super.setup();
        provideSpreadsheetEnv({
            showHistory: this.showHistory.bind(this),
        });
    }
}

registry
    .category("actions")
    .add("spreadsheet_test_action", SpreadsheetTestAction, { force: true });
