/** @odoo-module native */
import { DocumentsCogMenuItem } from "@document/views/cog_menu/document_cog_menu_item";
import { useService } from "@web/core/utils/hooks";
import { useSearchModel } from "@web/search/search_model";

export class DocumentsCogMenuItemAiAutoSort extends DocumentsCogMenuItem {
    static template = "ai_document.DocumentsCogMenuItemAiAutoSort";

    setup() {
        super.setup();
        this.searchModel = useSearchModel();
        this.action = useService("action");
        this.folder = this.searchModel.getSelectedFolder();
    }

    async onSelected() {
        if (!this.folder || typeof this.folder.id !== "number") {
            return;
        }

        this.action.doAction("ai_document.ai_documents_sort_action", {
            additionalContext: {
                default_folder_id: this.folder.id,
            },
            onClose: async () => {
                await this.searchModel._reloadSearchPanel();
            },
        });
    }
}
