/** @odoo-module native */
import { DocumentsFileViewer } from "@document/attachments/document_file_viewer";
import { patch } from "@web/core/utils/patch";

patch(DocumentsFileViewer.prototype, {
    /**
     * Do not show the Split PDF option for embedded PDF in XML invoices.
     */
    get hasSplitPdf() {
        if (this.documentService.documentList?.initialRecordSelectionLength === 1) {
            if (
                this.documentService.documentList.selectedDocument.record.data
                    .has_embedded_pdf
            ) {
                return false;
            }
        } else if (
            this.documentService.documentList?.documents.some(
                (document) => document.record.data.has_embedded_pdf,
            )
        ) {
            return false;
        }
        return super.hasSplitPdf;
    },
});
