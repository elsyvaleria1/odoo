/** @odoo-module native */
import { t } from "@odoo/owl";
import { ConfirmationDialog } from "@web/ui/dialog";

export class RestoreVersionConfirmationDialog extends ConfirmationDialog {
    static template = "spreadsheet_edition.RestoreVersionConfirmationDialog";
    static props = { ...ConfirmationDialog.props, makeACopy: t.function() };

    async _makeACopy() {
        return this.execButton(this.props.makeACopy);
    }
}
