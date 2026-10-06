/** @odoo-module native */
import { DocumentsAction } from "@document/views/action/document_action";
import { patch } from "@web/core/utils/patch";

patch(DocumentsAction.prototype, {
    isPreviewAction(action) {
        return super.isPreviewAction(action) && action.key !== "insert";
    },
});
