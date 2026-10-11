/** @odoo-module native */
import { documentActions } from "@document/views/document_actions";
import { patch } from "@web/core/utils/patch";

patch(documentActions.download, {
    isVisible(documentService, data) {
        return super.isVisible(documentService, data) && data.handler !== "spreadsheet";
    },
});
