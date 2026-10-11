/** @odoo-module native */
import { documentPreview } from "@document/attachments/document_file";
import { XLSX_MIME_TYPES } from "@document_spreadsheet/helpers";
import { patch } from "@web/core/utils/patch";

patch(documentPreview, {
    isViewable(data) {
        return (
            ["spreadsheet", "frozen_spreadsheet"].includes(data.handler) ||
            XLSX_MIME_TYPES.includes(data.mimetype) ||
            data.mimetype === "text/csv" ||
            super.isViewable(data)
        );
    },
});
