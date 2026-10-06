/** @odoo-module native */
import { SelectAddDocumentCreateDialog } from "@document/views/view_dialogs/select_add_document_create_dialog";
import { createXlsxAttachment } from "@document_spreadsheet/helpers";
import { useAppContext } from "@web/core/app_context";
import { patch } from "@web/core/utils/patch";

patch(SelectAddDocumentCreateDialog.prototype, {
    setup() {
        super.setup(...arguments);
        this.appContext = useAppContext();
    },
    /**
     * Convert Odoo Spreadsheet to .xlsx format
     */
    async _processAttachments(attachmentRecords) {
        return createXlsxAttachment(this.appContext, this.orm, attachmentRecords);
    },
});
