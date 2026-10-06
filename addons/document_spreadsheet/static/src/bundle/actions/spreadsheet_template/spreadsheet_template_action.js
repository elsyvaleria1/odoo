/** @odoo-module native */
import { provideSpreadsheetEnv } from "@spreadsheet/hooks";
import { AbstractSpreadsheetAction } from "@spreadsheet_edition/bundle/actions/abstract_spreadsheet_action";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

export class SpreadsheetTemplateAction extends AbstractSpreadsheetAction {
    static template = "document_spreadsheet.SpreadsheetTemplateAction";
    resModel = "spreadsheet.template";
    threadField = "template_id";

    setup() {
        super.setup();
        provideSpreadsheetEnv({
            newSpreadsheet: this.createNewSpreadsheet.bind(this),
            makeCopy: this.makeCopy.bind(this),
        });
    }

    /**
     * Create a new empty spreadsheet template
     * @returns {Promise<number>} id of the newly created spreadsheet template
     */
    async createNewSpreadsheet() {
        const data = {
            name: _t("Untitled spreadsheet template"),
        };
        const id = await this.orm.create("spreadsheet.template", [data]);
        this._openSpreadsheet(id);
        return id;
    }
}

registry
    .category("actions")
    .add("action_view_template", SpreadsheetTemplateAction, { force: true });
