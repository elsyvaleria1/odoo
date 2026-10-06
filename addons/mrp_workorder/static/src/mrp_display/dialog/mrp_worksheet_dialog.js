/** @odoo-module native */
import { HtmlField } from "@html_editor/fields/html_field";
import DocumentViewer from "@mrp_workorder/components/viewer";
import { t } from "@odoo/owl";
import { ConfirmationDialog } from "@web/ui/dialog";

export class MrpWorksheetDialog extends ConfirmationDialog {
    static props = {
        ...ConfirmationDialog.props,
        body: t.any().optional(),
        worksheetData: t.or([t.object(), t.boolean()]),
        record: t.object(),
    };
    static template = "mrp_workorder.MrpWorksheetDialog";
    static components = {
        ...ConfirmationDialog.components,
        DocumentViewer,
        HtmlField,
    };

    get htmlInfo() {
        return {
            name: "note",
            record: this.props.record,
            readonly: true,
            embeddedComponents: true,
        };
    }
}
