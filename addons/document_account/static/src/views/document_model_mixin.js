/** @odoo-module native */
import { DocumentsKanbanModel } from "@document/views/kanban/document_kanban_model";
import { DocumentsListModel } from "@document/views/list/document_list_model";
import { patch } from "@web/core/utils/patch";

// Factory: each patch() call must receive its own fresh extension object
// (patch() mutates it to build the `super` chain), so this is applied to
// several record prototypes (see also documents_activity_model.js).
export const AccountIsViewablePatch = () => ({
    /**
     * @override
     */
    isViewable() {
        if (this.data.mimetype.endsWith("/xml") && this.data.has_embedded_pdf) {
            return true;
        }
        return super.isViewable(...arguments);
    },
});

patch(DocumentsKanbanModel.Record.prototype, AccountIsViewablePatch());
patch(DocumentsListModel.Record.prototype, AccountIsViewablePatch());
