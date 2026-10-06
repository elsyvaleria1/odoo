/** @odoo-module native */
import { DocumentsListController } from "@document/views/list/document_list_controller";
import { patch } from "@web/core/utils/patch";

patch(DocumentsListController.prototype, {
    get internalOnlyColumns() {
        return super.internalOnlyColumns.concat(["website_id"]);
    },
});
