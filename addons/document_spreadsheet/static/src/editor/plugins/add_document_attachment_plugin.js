/** @odoo-module native */
import { AddDocumentsAttachmentPlugin } from "@document/editor/plugins/add_document_attachment_plugin";
import { createXlsxAttachment } from "@document_spreadsheet/helpers";
import { patch } from "@web/core/utils/patch";

patch(AddDocumentsAttachmentPlugin.prototype, {
    /**
     * Convert Odoo Spreadsheet to .xlsx format
     */
    async _processAttachments(attachmentRecords) {
        return createXlsxAttachment(
            this.config.embeddedComponentInfo?.env,
            this.services.orm,
            attachmentRecords,
        );
    },
});
