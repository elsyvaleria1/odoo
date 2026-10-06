/** @odoo-module native */
import { proxy, t } from "@odoo/owl";
import { omit } from "@web/core/utils/collections/objects";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";

export class SpreadsheetCloneCSVXlsxDialog extends ConfirmationDialog {
    static template = "document_spreadsheet.SpreadsheetCloneCSVXlsxDialog";
    static props = {
        ...omit(ConfirmationDialog.props, "body", "confirm"),
        documentId: t.number(),
    };

    setup() {
        super.setup();
        this.archiveDocumentState = proxy({ willArchive: true });
        this.action = useService("action");
        this.orm = useService("orm");
    }

    /**
     * @override
     */
    async confirm() {
        this.execButton(async () => {
            // Replacing call to a props-provided `confirm` method with the
            // archiving behavior makes a more unified component.
            const spreadsheetId = await this.orm.call(
                "document.document",
                "import_to_spreadsheet",
                [this.props.documentId],
                { archive_source: this.archiveDocumentState.willArchive },
            );
            this.action.doAction({
                type: "ir.actions.client",
                tag: "action_view_spreadsheet",
                params: {
                    spreadsheet_id: spreadsheetId,
                },
            });
        });
    }
}
