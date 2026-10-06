/** @odoo-module native */
import { t } from "@odoo/owl";
import { TextField } from "@web/fields/basic/text/text_field";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpLogNoteDialog extends ConfirmationDialog {
    static template = "mrp_workorder.MrpLogNoteDialog";
    static props = {
        ...ConfirmationDialog.props,
        record: t.object(),
        reload: t.function().optional(),
    };
    static components = {
        ...ConfirmationDialog.components,
        TextField,
    };

    async cancel() {
        this.props.record.save();
        this.props.close();
    }
}
