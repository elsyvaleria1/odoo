/** @odoo-module native */
import { documentActions } from "@document/views/document_actions";
import { patch } from "@web/core/utils/patch";

// a spreadsheet is opened, not downloaded: on a row and in the cog menu alike
patch(documentActions.download, {
    isVisible(documentService, data) {
        return super.isVisible(documentService, data) && data.handler !== "spreadsheet";
    },
});
